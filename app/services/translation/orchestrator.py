"""Translation orchestrator: a persisted state machine over ``TranslationStatus`` (as ``migration_v2/orchestrator.py``).

The happy path:

    PENDING → PREPARING → TRANSLATING → CHECKING (⇄ REPAIRING) → RENDERING → REVIEW_PENDING → APPROVED

All state lives in the ``TranslationStore``: ``resume_incomplete`` re-queues every job that was mid-stage, and that
stage runs again. Each job runs in its own asyncio task behind a semaphore; cancellation is cooperative and takes
effect between stages. A status without a stage (TRANSLATING until Phase T5) leaves the job waiting there.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from loguru import logger

from app.schemas.v2 import ArtifactKind, LanguageCode, TranslationJob, TranslationStatus
from app.services.migration_v2.artifacts import ArtifactWriter
from app.services.migration_v2.audit import audited, write_calls
from app.services.migration_v2.orchestrator import JobStateError

from .stages import SYSTEM_ACTOR, Stage, TranslationStageContext, default_stages

NEXT_STATUS: dict[TranslationStatus, TranslationStatus] = {
    TranslationStatus.PENDING: TranslationStatus.PREPARING,
    TranslationStatus.PREPARING: TranslationStatus.TRANSLATING,
    TranslationStatus.TRANSLATING: TranslationStatus.CHECKING,
    TranslationStatus.CHECKING: TranslationStatus.RENDERING,
    TranslationStatus.REPAIRING: TranslationStatus.CHECKING,
    TranslationStatus.RENDERING: TranslationStatus.REVIEW_PENDING,
}

WORK_STAGES: tuple[TranslationStatus, ...] = (
    TranslationStatus.PREPARING,
    TranslationStatus.TRANSLATING,
    TranslationStatus.CHECKING,
    TranslationStatus.REPAIRING,
    TranslationStatus.RENDERING,
)
WAITING_FOR_HUMAN = frozenset({TranslationStatus.REVIEW_PENDING})
RUNNABLE = (TranslationStatus.PENDING, *WORK_STAGES)

# Artifacts a stage needs; a retry from that stage is refused without them.
STAGE_REQUIRES: dict[TranslationStatus, tuple[ArtifactKind, ...]] = {
    status: (ArtifactKind.SEGMENTS,) for status in WORK_STAGES if status != TranslationStatus.PREPARING
}
RETRYABLE_FROM = frozenset(
    {TranslationStatus.FAILED_TECHNICAL, TranslationStatus.CANCELLED, TranslationStatus.REVIEW_PENDING}
)


def new_job_id() -> str:
    return f"TRN-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"


class TranslationOrchestrator:
    def __init__(
        self,
        store: Any,
        artifacts: ArtifactWriter,
        migrations: Any,
        migration_artifacts: ArtifactWriter,
        glossaries: Any = None,
        language_templates: Any = None,
        settings: Any = None,
        stages: Optional[dict[TranslationStatus, Stage]] = None,
        rate_limiter: Any = None,
        chain_factory: Any = None,
        max_concurrent_jobs: int = 2,
    ):
        self.store = store
        self.artifacts = artifacts
        self.migrations = migrations
        self.migration_artifacts = migration_artifacts
        self.glossaries = glossaries
        self.language_templates = language_templates
        self.settings = settings
        self.stages: dict[TranslationStatus, Stage] = {**default_stages(), **(stages or {})}
        self.rate_limiter = rate_limiter
        self.chain_factory = chain_factory
        self._max_concurrent = max_concurrent_jobs
        self._slots: Optional[asyncio.Semaphore] = None
        self._tasks: dict[str, asyncio.Task] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> list[str]:
        """Resume every job a previous process left mid-run."""
        return self.resume_incomplete()

    async def stop(self) -> None:
        """Cancel running tasks. Statuses stay as they are, so the jobs resume on the next start."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def resume_incomplete(self) -> list[str]:
        resumed = []
        # A status without a stage yet has nothing to resume.
        runnable = [s for s in RUNNABLE if s == TranslationStatus.PENDING or s in self.stages]
        for job_id in self.store.job_ids_with_status(runnable):
            if self.submit(job_id):
                self.store.add_event(job_id, "resumed", SYSTEM_ACTOR)
                resumed.append(job_id)
        if resumed:
            logger.info(f"Translation orchestrator resumed {len(resumed)} job(s): {resumed}")
        return resumed

    def is_running(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return task is not None and not task.done()

    def submit(self, job_id: str) -> bool:
        """Start the job's task unless it is already running."""
        if self.is_running(job_id):
            return False
        task = asyncio.create_task(self._run(job_id), name=f"translation:{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda t, jid=job_id: self._tasks.pop(jid, None) if self._tasks.get(jid) is t else None)
        return True

    async def wait(self, job_id: str, timeout: float = 30.0) -> TranslationJob:
        """Wait until the job's task finishes (tests and scripts)."""
        task = self._tasks.get(job_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout)
        return self.store.get_job(job_id)

    # ── Commands ──────────────────────────────────────────────────────

    def create(
        self,
        migration_job_id: str,
        language: LanguageCode | str,
        glossary: Optional[tuple[str, int]] = None,
        language_template: Optional[tuple[str, int]] = None,
        created_by: Optional[str] = None,
        submit: bool = True,
    ) -> TranslationJob:
        job = TranslationJob(
            job_id=new_job_id(),
            migration_job_id=migration_job_id,
            language=language,
            glossary_id=glossary[0] if glossary else None,
            glossary_version=glossary[1] if glossary else None,
            language_template_id=language_template[0] if language_template else None,
            language_template_version=language_template[1] if language_template else None,
            created_by=created_by,
        )
        job = self.store.create_job(job)
        if submit:
            self.submit(job.job_id)
        return job

    def _job(self, job_id: str) -> TranslationJob:
        job = self.store.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def cancel(self, job_id: str, actor: Optional[str]) -> TranslationJob:
        job = self._job(job_id)
        if job.is_terminal:
            raise JobStateError("JOB_FINISHED", f"Job {job_id} is already {job.status.value}")
        if self.is_running(job_id):
            # Cooperative: the run loop stops before the next stage.
            self.store.update_job(job_id, cancel_requested=1)
            self.store.add_event(job_id, "cancel_requested", actor)
        else:
            self.store.set_status(job_id, TranslationStatus.CANCELLED, actor, "cancelled", expected=job.status)
        return self._job(job_id)

    def retry(self, job_id: str, from_stage: Optional[TranslationStatus], actor: Optional[str]) -> TranslationJob:
        job = self._job(job_id)
        if self.is_running(job_id):
            raise JobStateError("JOB_RUNNING", f"Job {job_id} is running")
        if job.status not in RETRYABLE_FROM:
            raise JobStateError("NOT_RETRYABLE", f"Job {job_id} is {job.status.value}; nothing to retry")
        if from_stage is None:
            failed = (self.store.get_job_row(job_id) or {}).get("failed_stage")
            from_stage = TranslationStatus(failed) if failed else TranslationStatus.PREPARING
        if from_stage not in WORK_STAGES:
            raise JobStateError("INVALID_STAGE",
                                f"{from_stage.value} is not a stage; use one of {[s.value for s in WORK_STAGES]}")
        missing = [k.value for k in STAGE_REQUIRES.get(from_stage, ()) if job.latest_artifact(k) is None]
        if missing:
            raise JobStateError("MISSING_ARTIFACTS", f"Cannot start at {from_stage.value}: no {', '.join(missing)} yet")
        self.store.update_job(job_id, error=None, failed_stage=None, cancel_requested=0)
        self.store.set_status(job_id, from_stage, actor, "retry", {"from_status": job.status.value}, expected=job.status)
        self.submit(job_id)
        return self._job(job_id)

    # ── Run loop ──────────────────────────────────────────────────────

    async def _run(self, job_id: str) -> None:
        if self._slots is None:
            self._slots = asyncio.Semaphore(self._max_concurrent)
        async with self._slots:
            while True:
                job = self.store.get_job(job_id)
                if job is None or job.is_terminal or job.status in WAITING_FOR_HUMAN:
                    return
                if (self.store.get_job_row(job_id) or {}).get("cancel_requested"):
                    self.store.set_status(job_id, TranslationStatus.CANCELLED, SYSTEM_ACTOR, "cancelled",
                                          expected=job.status)
                    return

                status = job.status
                if status == TranslationStatus.PENDING:
                    self.store.set_status(job_id, NEXT_STATUS[status], SYSTEM_ACTOR, "advanced", expected=status)
                    continue

                stage = self.stages.get(status)
                if stage is None:  # not built yet (TRANSLATING until T5): the job waits here
                    return
                ctx = TranslationStageContext(
                    job=job, store=self.store, artifacts=self.artifacts, migrations=self.migrations,
                    migration_artifacts=self.migration_artifacts, glossaries=self.glossaries,
                    language_templates=self.language_templates, settings=self.settings,
                    rate_limiter=self.rate_limiter, chain_factory=audited(self.chain_factory),
                )
                self.store.add_event(job_id, "stage_started", SYSTEM_ACTOR, {"stage": status.value})
                try:
                    override = await stage(ctx)
                    write_calls(self.store, job_id, SYSTEM_ACTOR, ctx.chain_factory, status.value)
                except asyncio.CancelledError:
                    write_calls(self.store, job_id, SYSTEM_ACTOR, ctx.chain_factory, status.value)
                    self.store.add_event(job_id, "interrupted", SYSTEM_ACTOR, {"stage": status.value})
                    raise
                except Exception as exc:  # technical failure: record it and stop
                    write_calls(self.store, job_id, SYSTEM_ACTOR, ctx.chain_factory, status.value)
                    logger.exception(f"Translation {job_id} failed in {status.value}")
                    message = getattr(exc, "message", None) or str(exc) or type(exc).__name__
                    self.store.update_job(job_id, error=message, failed_stage=status.value)
                    self.store.set_status(
                        job_id, TranslationStatus.FAILED_TECHNICAL, SYSTEM_ACTOR, "failed",
                        {"stage": status.value, "error": message}, expected=status,
                    )
                    return

                nxt = override or NEXT_STATUS[status]
                self.store.set_status(job_id, nxt, SYSTEM_ACTOR, "advanced", {"stage": status.value}, expected=status)
