"""Integration tests for JobManager."""

import pytest
import asyncio
from unittest.mock import MagicMock
from app.services.job_manager import JobManager
from app.schemas.jobs import JobStatus
from app.config.settings import Settings


@pytest.mark.asyncio
async def test_job_manager_lifecycle():
    """Test that jobs can be queued, processed, and tracked."""
    settings = Settings(upload_dir="test_uploads", output_dir="test_output")
    manager = JobManager(settings, concurrency=1)
    
    # We mock _process_document so we don't actually run extraction during the unit test
    async def mock_process_document(job_id, document_id):
        job = manager.get_job(job_id)
        doc = next(d for d in job.documents if d.document_id == document_id)
        doc.status = JobStatus.COMPLETED
        doc.progress_percentage = 100
        
        all_done = all(d.status in (JobStatus.COMPLETED, JobStatus.FAILED) for d in job.documents)
        if all_done:
            job.status = JobStatus.COMPLETED
            
    manager._process_document = mock_process_document
    
    await manager.start()
    
    job = manager.create_batch_job(["doc1", "doc2"])
    assert job.status == JobStatus.QUEUED
    assert len(job.documents) == 2
    
    # Wait for processing
    await asyncio.sleep(0.5)
    
    assert job.status == JobStatus.COMPLETED
    assert job.documents[0].status == JobStatus.COMPLETED
    assert job.documents[1].status == JobStatus.COMPLETED
    
    await manager.stop()
