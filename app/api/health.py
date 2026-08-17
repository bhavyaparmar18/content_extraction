"""Health-check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Return service status — used by load balancers and monitoring."""
    return {
        "status": "healthy",
        "service": "sop-migration-system",
        "version": "0.1.0",
    }
