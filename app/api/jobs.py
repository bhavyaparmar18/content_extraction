"""Endpoints for polling and streaming job status."""

import asyncio
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger

from app.schemas.jobs import BatchJob

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=BatchJob)
async def get_job_status(job_id: str, request: Request):
    """Poll for the current status of a batch job."""
    job_manager = request.app.state.job_manager
    job = job_manager.get_job(job_id)
    if not job:
        logger.warning("Job status requested for unknown job '{j}'.", j=job_id)
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.websocket("/{job_id}/progress")
async def websocket_job_progress(websocket: WebSocket, job_id: str):
    """Stream real-time progress updates for a batch job."""
    await websocket.accept()
    job_manager = websocket.app.state.job_manager
    job = job_manager.get_job(job_id)
    
    if not job:
        await websocket.close(code=1008, reason="Job not found")
        return
        
    try:
        while True:
            # Send current state
            await websocket.send_json(job.model_dump(mode='json'))
            
            # If done, exit loop
            if job.status in ("completed", "failed"):
                break
                
            # Wait before polling again
            await asyncio.sleep(1.0)
            
    except WebSocketDisconnect:
        # Client disconnected
        logger.debug("WebSocket client disconnected from job '{j}' progress.", j=job_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("WebSocket progress stream failed for job '{j}'.", j=job_id)
        await websocket.close(code=1011, reason=str(e))
