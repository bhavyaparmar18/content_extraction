"""Phase T5: the translator (groups, waves and memory, prompts, answers) and the TRANSLATING, CHECKING and
REPAIRING stages on the fixture migration, with a fake LLM."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.schemas.v2 import (
    ArtifactKind,
    Glossary,
    GlossaryEntry,
    QualityReport,
    Segment,
    SegmentKind,
    SegmentLocator,
    SegmentOrigin,
    SegmentSet,
    TranslationSet,
    TranslationStatus,
)
from app.schemas.v2.refs import REF_TOKEN_PATTERN
from app.services.llm.prompts.v2.translator import SYSTEM_PROMPT
from app.services.migration_v2.audit import describe
from app.services.migration_v2.orchestrator import JobStateError
from app.services.translation.checks import copy_only
from app.services.translation.stages import default_stages
from app.services.translation.translator import (
    TranslatedSegment,
    Translator,
    TranslatorOutput,
    group_segments,
    merged,
    translate_all,
)
from tests.test_translation_jobs import _env, asked, translating
from tests.test_v2_drafter import FakeChain, FakeFactory
from tests.test_v2_renderer import tpl  # noqa: F401  (fixture)

def _seg(n: int, kind: SegmentKind, text: str, scope: str = "TGT-1") -> Segment:
    locator = {
        SegmentKind.CLAIM: dict(section_id=scope, slot_id=f"{scope}-S1", claim_id=f"C-{n}"),
        SegmentKind.TABLE_CELL: dict(section_id=scope, unit_id="U1", row=1, col=n),
        SegmentKind.TABLE_HEADER: dict(section_id=scope, unit_id="U1", col=n),
        SegmentKind.XREF: dict(section_id=scope, claim_id="C-1", ref_index=0),
        SegmentKind.TEMPLATE_TEXT: dict(block_path=f"body/p[{n}]"),
    }[kind]
    return Segment(segment_id=f"SEG-{n:04d}", kind=kind, source_text=text, locator=SegmentLocator(**locator))


def _glossary(**kw) -> Glossary:
    return Glossary(glossary_id="g", version=1, language="de-DE", name="Terms", entries=[
        GlossaryEntry(source_term="deviation", target_term="Abweichung"),
        GlossaryEntry(source_term="batch record", target_term="Chargenprotokoll"),
        GlossaryEntry(source_term="SAP", do_not_translate=True, case_sensitive=True),
    ], **kw)


# ── Groups, waves, prompts, answers ───────────────────────────────────


def test_each_text_is_translated_once_and_texts_without_words_are_copied():
    segments = [_seg(1, SegmentKind.CLAIM, "Record every deviation."), _seg(2, SegmentKind.TABLE_CELL, "QA Manager"),
                _seg(3, SegmentKind.TABLE_CELL, "QA Manager", "TGT-2"), _seg(4, SegmentKind.TABLE_CELL, "1.2")]
    groups = group_segments(segments)
    assert [g.key for g in groups] == ["SEG-0001", "SEG-0002", "SEG-0004"]
    assert groups[1].segment_ids == ["SEG-0002", "SEG-0003"] and groups[1].scope == "TGT-1"
    assert groups[0].role == "paragraph" and groups[1].role == "table cell" and groups[0].wave == 2

    assert copy_only("1.2") and copy_only("BI-VQD-10095-S") and copy_only("{{ref:SRC-1}} ⟦1⟧") and copy_only("  ")
    assert copy_only("SAP", _glossary()) and not copy_only("SAP") and not copy_only("Record every deviation.")
    assert not copy_only("SAP system", _glossary())


@pytest.mark.asyncio
async def test_the_first_wave_gives_the_second_its_memory():
    segments = [_seg(1, SegmentKind.TEMPLATE_TEXT, "Purpose"), _seg(2, SegmentKind.CLAIM, "State the purpose here."),
                _seg(3, SegmentKind.CLAIM, "Keep the records.", "TGT-2")]
    groups = group_segments(segments)
    chain = FakeChain(translating(lambda key, text, repair: "Zweck" if text == "Purpose" else f"DE {text}"))
    translator = Translator("de-DE", groups)
    run = await translate_all(translator, groups, FakeFactory(TranslatorOutput=chain), block_tokens=10)
    assert run.targets == {"SEG-0001": "Zweck", "SEG-0002": "DE State the purpose here.",
                           "SEG-0003": "DE Keep the records."}
    assert run.memory_pairs == 1 and run.calls == run.blocks == 3 and run.usage["calls"] == 3
    prompts = {asked(c[-1].content)[0][0]: c[-1].content for c in chain.calls}
    assert [asked(c[-1].content)[0][0] for c in chain.calls][0] == "SEG-0001"  # the first wave first
    assert '"Purpose" → "Zweck"' in prompts["SEG-0002"] and "ALREADY TRANSLATED" in prompts["SEG-0002"]
    assert "ALREADY TRANSLATED" not in prompts["SEG-0003"]  # the block does not use the term
    assert "ALREADY TRANSLATED" not in prompts["SEG-0001"]

    translator.memory_tokens = 1
    assert translator.memory_terms(translator.blocks(groups[1:2])[0]) == []  # over the cap


def test_the_prompt_has_the_batch_glossary_terms_and_style_notes_only():
    groups = group_segments([_seg(1, SegmentKind.CLAIM, "Record every deviation in SAP.")])
    with_glossary = Translator("de-DE", groups, _glossary(style_notes="Address the reader as Sie."))
    prompt = with_glossary.prompt(with_glossary.blocks(groups)[0])
    assert prompt.startswith("TARGET LANGUAGE: German (de-DE)")
    assert '"deviation" → "Abweichung"' in prompt and '"SAP": DO NOT TRANSLATE' in prompt
    assert "Chargenprotokoll" not in prompt and "Address the reader as Sie." in prompt
    assert "[SEG-0001] (paragraph) Record every deviation in SAP." in prompt

    free = Translator("ja-JP", groups)
    plain = free.prompt(free.blocks(groups)[0])
    assert "GLOSSARY" not in plain and "STYLE NOTES" not in plain and "TARGET LANGUAGE: Japanese (ja-JP)" in plain

    call = describe([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=plain)])
    assert (call["task"], call["prompt_version"], call["segment_ids"], call["retry"]) == (
        "translator", "translator/1", ["SEG-0001"], False)
    block = free.blocks(groups)[0]
    repair = describe([SystemMessage(content=SYSTEM_PROMPT),
                       HumanMessage(content=free.repair_prompt(block, {"SEG-0001": "x"}, {"SEG-0001": ["lost y"]}))])
    assert repair["task"] == "translator_repair" and repair["retry"]


def test_answers_are_matched_to_the_asked_segments():
    groups = group_segments([_seg(1, SegmentKind.TEMPLATE_TEXT, "Line one\nLine two"),
                             _seg(2, SegmentKind.TEMPLATE_TEXT, " Note "),
                             _seg(3, SegmentKind.TEMPLATE_TEXT, "Scope")])
    translator = Translator("de-DE", groups)
    block = translator.blocks(groups)[0]
    assert "[SEG-0001] (template text) Line one⏎Line two" in translator.prompt(block)
    out = translator.accept(block, TranslatorOutput(translations=[
        TranslatedSegment(segment_id="SEG-0001", translation="Zeile eins⏎Zeile zwei"),
        TranslatedSegment(segment_id="[SEG-0002]", translation="Hinweis"),
        TranslatedSegment(segment_id="SEG-0002", translation="second answer"),
        TranslatedSegment(segment_id="SEG-0003", translation="  "),
        TranslatedSegment(segment_id="SEG-0099", translation="not asked"),
    ]))
    assert out == {"SEG-0001": "Zeile eins\nZeile zwei", "SEG-0002": " Hinweis "}

    # Markers the English does not have are dropped; its own stay (the checks judge them).
    tagged = group_segments([_seg(1, SegmentKind.TEMPLATE_TEXT, "⟦1⟧Note:⟦/1⟧ keep it."),
                             _seg(2, SegmentKind.CLAIM, "Use the term.")])
    translator = Translator("ja-JP", tagged)
    out = translator.accept(translator.blocks(tagged)[0], TranslatorOutput(translations=[
        TranslatedSegment(segment_id="SEG-0001", translation="⟦1⟧注記：⟦/1⟧ ⟦2⟧保管⟦/2⟧する。"),
        TranslatedSegment(segment_id="SEG-0002", translation="その⟦1⟧用語⟦/1⟧を使用する。"),
    ]))
    assert out == {"SEG-0001": "⟦1⟧注記：⟦/1⟧ 保管する。", "SEG-0002": "その用語を使用する。"}


@pytest.mark.asyncio
async def test_a_failed_call_leaves_its_segments_untranslated():
    groups = group_segments([_seg(1, SegmentKind.CLAIM, "Keep the records."),
                             _seg(2, SegmentKind.CLAIM, "Sign the form.", "TGT-2")])

    def respond(prompt, n):
        return RuntimeError("timeout") if "SEG-0002" in prompt else translating()(prompt, n)

    run = await translate_all(Translator("fr-FR", groups), groups, FakeFactory(TranslatorOutput=FakeChain(respond)),
                              block_tokens=10)
    assert run.targets == {"SEG-0001": "FR Keep the records."}
    assert (run.calls, run.failed_calls, run.all_failed) == (2, 1, False)


@pytest.mark.asyncio
async def test_a_failed_block_is_tried_again_as_two_halves():
    groups = group_segments([_seg(n, SegmentKind.TABLE_CELL, f"Cell {n} text") for n in range(1, 5)])

    def respond(prompt, n):  # a long list runs away; two cells at a time are fine
        return RuntimeError("length limit was reached") if len(asked(prompt)) > 2 else translating()(prompt, n)

    run = await translate_all(Translator("fr-FR", groups), groups, FakeFactory(TranslatorOutput=FakeChain(respond)))
    assert run.targets == {f"SEG-{n:04d}": f"FR Cell {n} text" for n in range(1, 5)}
    assert (run.calls, run.failed_calls) == (3, 1)

    always = FakeFactory(TranslatorOutput=FakeChain(lambda p, n: RuntimeError("down")))
    run = await translate_all(Translator("fr-FR", groups), groups, always)
    assert run.targets == {} and run.all_failed and run.calls == 3  # the halves are not split again


@pytest.mark.asyncio
async def test_segments_an_answer_leaves_out_are_asked_again_once():
    groups = group_segments([_seg(n, SegmentKind.TABLE_CELL, f"Cell {n} text") for n in range(1, 5)])
    chain = FakeChain(translating(lambda key, text, repair: "" if key == "SEG-0004" else f"FR {text}"))
    run = await translate_all(Translator("fr-FR", groups), groups, FakeFactory(TranslatorOutput=chain))
    assert set(run.targets) == {"SEG-0001", "SEG-0002", "SEG-0003"} and run.left_out == 1
    assert [[k for k, _ in asked(c[-1].content)] for c in chain.calls] == [
        ["SEG-0001", "SEG-0002", "SEG-0003", "SEG-0004"], ["SEG-0004"]]  # once more, then left for the checks


# ── The stages on the fixture migration ───────────────────────────────


def _latest_sets(env, job, segment_set):
    return [env.orch.artifacts.latest(job, ArtifactKind.TRANSLATION, TranslationSet, s) for s in segment_set.scopes]


def _current(env, job) -> SegmentSet:
    segment_set = env.orch.artifacts.latest(job, ArtifactKind.SEGMENTS, SegmentSet)
    return merged(segment_set, [s for s in _latest_sets(env, job, segment_set) if s is not None])


def _events(env, job_id) -> list[dict]:
    return env.store.list_events(job_id)


@pytest.mark.asyncio
async def test_a_job_is_translated_checked_and_waits_at_rendering(tpl, tmp_path):  # noqa: F811
    chain = FakeChain(translating())
    env = _env(tmp_path, tpl, FakeFactory(TranslatorOutput=chain))
    job = await env.orch.wait(env.orch.create(env.migration.job_id, "fr-FR").job_id)
    assert job.status == TranslationStatus.RENDERING, job.error

    segment_set = env.orch.artifacts.latest(job, ArtifactKind.SEGMENTS, SegmentSet)
    assert {a.scope for a in job.artifacts if a.kind == ArtifactKind.TRANSLATION} == set(segment_set.scopes)
    sets = _latest_sets(env, job, segment_set)
    assert {s.prompt_version for s in sets} == {"translator/1"} and {s.model for s in sets} == {"azure/fake"}
    current = merged(segment_set, sets)
    assert len(current.segments) == len(segment_set.segments)
    llm = [s for s in current.segments if s.origin == SegmentOrigin.LLM]
    copied = [s for s in current.segments if s.origin == SegmentOrigin.COPIED]
    assert len(llm) + len(copied) == len(current.segments) and llm
    assert all(s.target_text == f"FR {s.source_text}" for s in llm)
    assert all(s.target_text == s.source_text for s in copied)

    # Each distinct text was asked for once.
    keys = [k for call in chain.calls for k, _ in asked(call[-1].content)]
    assert len(keys) == len(set(keys)) == len({s.source_text for s in llm})

    report = env.orch.artifacts.latest(job, ArtifactKind.QUALITY_REPORT, QualityReport, "translation")
    assert report.version == 1 and report.unit_coverage == 1.0 and not report.open_gate_issues
    assert not [i for i in report.issues if i.severity.value in ("critical", "high", "medium")]
    events = _events(env, job.job_id)
    names = [e["event"] for e in events]
    assert {"translator", "checks"} <= set(names) and "repair" not in names
    calls = [e["detail"] for e in events if e["event"] == "llm_call"]
    assert calls and {c["task"] for c in calls} == {"translator"} and {c["stage"] for c in calls} == {"TRANSLATING"}
    assert {c["prompt_version"] for c in calls} == {"translator/1"}
    translator = next(e["detail"] for e in events if e["event"] == "translator")
    assert translator["missing"] == 0 and translator["copied"] == len({s.source_text for s in copied})

    # A job waiting at RENDERING can be cancelled and checked again.
    env.orch.cancel(job.job_id, None)
    env.orch.retry(job.job_id, TranslationStatus.CHECKING, "reviewer")
    job = await env.orch.wait(job.job_id)
    assert job.status == TranslationStatus.RENDERING
    assert env.orch.artifacts.latest(job, ArtifactKind.QUALITY_REPORT, QualityReport, "translation").version == 2


def _with_token(env, job) -> list[Segment]:
    return [s for s in _current(env, job).segments if REF_TOKEN_PATTERN.search(s.source_text)]


@pytest.mark.asyncio
async def test_a_lost_reference_token_is_repaired_once(tpl, tmp_path):  # noqa: F811
    def transform(key, text, repair):
        return f"FR {text}" if repair else f"FR {REF_TOKEN_PATTERN.sub('', text)}"

    env = _env(tmp_path, tpl, FakeFactory(TranslatorOutput=FakeChain(translating(transform))))
    job = await env.orch.wait(env.orch.create(env.migration.job_id, "fr-FR").job_id)
    assert job.status == TranslationStatus.RENDERING, job.error
    fixed = _with_token(env, job)
    assert fixed and all(s.origin == SegmentOrigin.REPAIR and s.target_text == f"FR {s.source_text}" for s in fixed)
    assert all(s.origin != SegmentOrigin.REPAIR for s in _current(env, job).segments if s not in fixed)

    names = [e["event"] for e in _events(env, job.job_id)]
    assert names.count("checks") == 2 and names.count("repair") == 1
    rounds = [e["detail"] for e in _events(env, job.job_id) if e["event"] == "checks"]
    assert rounds[0]["repair"] == len(fixed) and rounds[1]["repair"] == 0
    first = env.orch.artifacts.read_model(
        min((a for a in job.artifacts if a.kind == ArtifactKind.QUALITY_REPORT), key=lambda a: a.version), QualityReport)
    assert {i.issue_id.rsplit("-", 1)[-1] for i in first.issues if i.severity.value == "critical"} == {"REF_TOKENS"}
    last = env.orch.artifacts.latest(job, ArtifactKind.QUALITY_REPORT, QualityReport, "translation")
    assert not [i for i in last.issues if "REF_TOKENS" in i.issue_id]
    repair_calls = [e["detail"] for e in _events(env, job.job_id) if e["event"] == "llm_call"
                    and e["detail"]["stage"] == "REPAIRING"]
    assert repair_calls and {c["task"] for c in repair_calls} == {"translator_repair"}


@pytest.mark.asyncio
async def test_a_segment_that_fails_again_is_left_open_without_a_third_round(tpl, tmp_path):  # noqa: F811
    drop = lambda key, text, repair: f"FR {REF_TOKEN_PATTERN.sub('', text)}"  # noqa: E731
    env = _env(tmp_path, tpl, FakeFactory(TranslatorOutput=FakeChain(translating(drop))))
    job = await env.orch.wait(env.orch.create(env.migration.job_id, "fr-FR").job_id)
    assert job.status == TranslationStatus.RENDERING
    assert all(s.origin == SegmentOrigin.REPAIR for s in _with_token(env, job))
    names = [e["event"] for e in _events(env, job.job_id)]
    assert names.count("checks") == 2 and names.count("repair") == 1
    last = env.orch.artifacts.latest(job, ArtifactKind.QUALITY_REPORT, QualityReport, "translation")
    assert [i for i in last.issues if "REF_TOKENS" in i.issue_id and not i.resolved]


@pytest.mark.asyncio
async def test_a_worse_repair_keeps_the_previous_translation(tpl, tmp_path):  # noqa: F811
    def transform(key, text, repair):
        if not REF_TOKEN_PATTERN.search(text):
            return f"FR {text}"
        return REF_TOKEN_PATTERN.sub("", text) if repair else text  # first: left in English; repair: token lost

    env = _env(tmp_path, tpl, FakeFactory(TranslatorOutput=FakeChain(translating(transform))))
    job = await env.orch.wait(env.orch.create(env.migration.job_id, "fr-FR").job_id)
    assert job.status == TranslationStatus.RENDERING
    kept = _with_token(env, job)
    assert kept and all(s.origin == SegmentOrigin.REPAIR and s.target_text == s.source_text for s in kept)
    repair = next(e["detail"] for e in _events(env, job.job_id) if e["event"] == "repair")
    assert repair["kept_previous"] >= 1 and repair["improved"] == 0


@pytest.mark.asyncio
async def test_without_an_llm_the_job_fails(tpl, tmp_path):  # noqa: F811
    env = _env(tmp_path, tpl)
    env.orch.stages.update(default_stages())
    job = await env.orch.wait(env.orch.create(env.migration.job_id, "fr-FR").job_id)
    assert job.status == TranslationStatus.FAILED_TECHNICAL and "no LLM" in job.error
    assert env.store.get_job_row(job.job_id)["failed_stage"] == "TRANSLATING"

    with pytest.raises(JobStateError) as refused:
        env.orch.retry(job.job_id, TranslationStatus.CHECKING, None)
    assert refused.value.code == "MISSING_ARTIFACTS" and "translation" in refused.value.message


@pytest.mark.asyncio
async def test_when_every_call_fails_the_job_fails(tpl, tmp_path):  # noqa: F811
    down = _env(tmp_path, tpl, FakeFactory(TranslatorOutput=FakeChain(lambda p, n: RuntimeError("503"))))
    job = await down.orch.wait(down.orch.create(down.migration.job_id, "fr-FR").job_id)
    assert job.status == TranslationStatus.FAILED_TECHNICAL and "every translation call failed" in job.error
