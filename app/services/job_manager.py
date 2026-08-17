"""Background job manager for asynchronous document extraction."""

import asyncio
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from app.config.settings import Settings
from app.schemas.jobs import BatchJob, DocumentJob, JobStatus
from app.schemas.output import DocumentExtractionOutput, ExtractionStats, AssetManifest, AssetReference
from app.services.parser.parser_factory import ParserFactory
from app.services.extraction import TableExtractor, CrossPageTableStitcher, IconExtractor, CaptionExtractor
from app.services.hierarchy.ast_builder import ASTBuilder
from app.services.chunking.hierarchical import HierarchicalChunker
from app.services.chunking.semantic import SemanticChunker
from app.services.export.migration_exporter import MigrationExporter


class JobManager:
    """Manages background processing of document extraction jobs."""

    def __init__(self, settings: Settings, concurrency: int = 2):
        self.settings = settings
        self.concurrency = concurrency
        self.jobs: dict[str, BatchJob] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        
    async def start(self):
        """Start the background worker pool."""
        logger.info(f"Starting JobManager with {self.concurrency} workers.")
        for i in range(self.concurrency):
            task = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(task)
            
    async def stop(self):
        """Stop the background workers."""
        logger.info("Stopping JobManager workers...")
        for task in self.workers:
            task.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()

    def create_batch_job(self, document_ids: list[str]) -> BatchJob:
        """Create a new batch job and queue its documents."""
        job_id = str(uuid.uuid4())
        docs = []
        for did in document_ids:
            doc = DocumentJob(document_id=did, filename=f"{did}")
            docs.append(doc)
            
        job = BatchJob(job_id=job_id, documents=docs)
        self.jobs[job_id] = job
        
        # Enqueue each document
        for doc in docs:
            self.queue.put_nowait((job_id, doc.document_id))
            
        return job
        
    def get_job(self, job_id: str) -> Optional[BatchJob]:
        """Retrieve a job by ID."""
        return self.jobs.get(job_id)

    async def _worker(self, name: str):
        """Background worker loop to process documents."""
        while True:
            try:
                job_id, doc_id = await self.queue.get()
                await self._process_document(job_id, doc_id)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {name} encountered error: {e}")

    async def _process_document(self, job_id: str, document_id: str):
        """Process a single document through the extraction pipeline."""
        job = self.jobs.get(job_id)
        if not job:
            return
            
        doc_job = next((d for d in job.documents if d.document_id == document_id), None)
        if not doc_job:
            return
            
        doc_job.status = JobStatus.PROCESSING
        doc_job.started_at = datetime.utcnow()
        doc_job.message = "Started processing"
        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()
            
        try:
            # 1. Locate file
            upload_path = None
            for ext in self.settings.allowed_extensions:
                candidate = self.settings.upload_dir / f"{document_id}{ext}"
                if candidate.exists():
                    upload_path = candidate
                    break
                    
            if not upload_path:
                raise FileNotFoundError(f"File for document {document_id} not found.")
                
            doc_job.filename = upload_path.name
            doc_job.progress_percentage = 20
            
            # 2. Parse
            doc_job.message = "Parsing document..."
            factory = ParserFactory(settings=self.settings)
            parser = factory.get_parser(str(upload_path))
            # In a real async environment we might run this in a threadpool if it's blocking
            raw_document = await asyncio.to_thread(parser.parse, str(upload_path), document_id=document_id)
            doc_job.progress_percentage = 40
            
            # 3. Extraction
            doc_job.message = "Running extraction pipeline..."
            table_ext = TableExtractor(settings=self.settings)
            stitch_ext = CrossPageTableStitcher(settings=self.settings)
            icon_ext = IconExtractor(settings=self.settings)
            caption_ext = CaptionExtractor(settings=self.settings)

            raw_document = await asyncio.to_thread(table_ext.extract, raw_document)
            raw_document = await asyncio.to_thread(stitch_ext.extract, raw_document)
            raw_document = await asyncio.to_thread(icon_ext.extract, raw_document, document_id=document_id)
            raw_document = await asyncio.to_thread(caption_ext.extract, raw_document)
            doc_job.progress_percentage = 65
            
            # 4. AST Build
            doc_job.message = "Building Abstract Syntax Tree..."
            ast_builder = ASTBuilder(settings=self.settings)
            ast = await asyncio.to_thread(ast_builder.build, raw_document)
            doc_job.progress_percentage = 80

            # 5. Chunking
            doc_job.message = "Generating hierarchical and semantic chunks..."
            hierarchical_chunker = HierarchicalChunker(settings=self.settings)
            semantic_chunker = SemanticChunker(settings=self.settings)
            chunks = await asyncio.to_thread(hierarchical_chunker.chunk, ast)
            chunks = await asyncio.to_thread(semantic_chunker.chunk, chunks)
            doc_job.progress_percentage = 90
            
            # 6. Output packaging
            doc_job.message = "Finalizing output..."
            assets_manifest = self._build_asset_manifest(document_id, ast)
            migration_output = MigrationExporter.export(
                document_id=document_id,
                ast=ast,
                assets_manifest=assets_manifest,
            )
            
            # Save to disk
            output_dir = self.settings.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            out_file = output_dir / f"{document_id}_v2.json"
            
            # Write to disk using clean dictionary serialization without null/empty noise
            clean_json = json.dumps(migration_output.to_clean_dict(), indent=2, ensure_ascii=False)
            await asyncio.to_thread(out_file.write_text, clean_json, encoding="utf-8")
            
            doc_job.status = JobStatus.COMPLETED
            doc_job.progress_percentage = 100
            doc_job.message = "Successfully extracted document."
            doc_job.completed_at = datetime.utcnow()
            
        except Exception as e:
            logger.exception(f"Job {job_id} failed on doc {document_id}: {e}")
            doc_job.status = JobStatus.FAILED
            doc_job.error = str(e)
            doc_job.message = f"Failed: {str(e)}"
            doc_job.completed_at = datetime.utcnow()
            
        # Check if entire batch is complete
        all_done = all(d.status in (JobStatus.COMPLETED, JobStatus.FAILED) for d in job.documents)
        if all_done:
            job.status = JobStatus.COMPLETED if job.failed_documents == 0 else JobStatus.FAILED
            job.completed_at = datetime.utcnow()

    def _build_asset_manifest(self, document_id: str, ast) -> AssetManifest:
        """Build an asset manifest for images and icons in the document's asset directories."""
        node_meta = {}
        def _traverse_nodes(node):
            if getattr(node, "node_type", None) == "image":
                fname = Path(getattr(node, "asset_path", "")).name
                if fname:
                    node_meta[fname] = {
                        "width": getattr(node, "width", 0) or 0,
                        "height": getattr(node, "height", 0) or 0,
                    }
            elif getattr(node, "node_type", None) == "icon":
                fname = Path(getattr(node, "asset_path", "")).name
                if fname:
                    node_meta[fname] = {
                        "width": getattr(node, "width", 0) or 0,
                        "height": getattr(node, "height", 0) or 0,
                        "semantic_meaning": getattr(node, "semantic_meaning", None),
                    }
            for child in getattr(node, "children", []):
                _traverse_nodes(child)

        _traverse_nodes(ast)

        images = []
        icons = []
        img_dir = self.settings.get_document_image_dir(document_id)
        icon_dir = self.settings.get_document_icon_dir(document_id)

        if img_dir.exists():
            for f in img_dir.iterdir():
                if f.is_file():
                    meta = node_meta.get(f.name, {})
                    images.append(AssetReference(
                        asset_id=f.stem,
                        filename=f.name,
                        size_bytes=f.stat().st_size,
                        width=meta.get("width", 0),
                        height=meta.get("height", 0),
                    ))
        if icon_dir.exists():
            for f in icon_dir.iterdir():
                if f.is_file():
                    meta = node_meta.get(f.name, {})
                    icons.append(AssetReference(
                        asset_id=f.stem,
                        filename=f.name,
                        size_bytes=f.stat().st_size,
                        width=meta.get("width", 0),
                        height=meta.get("height", 0),
                        semantic_meaning=meta.get("semantic_meaning"),
                    ))

        return AssetManifest(
            base_path=str(self.settings.project_root / "data"),
            images=images,
            icons=icons,
        )
