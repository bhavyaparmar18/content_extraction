"""Schemas for the persistent SOP records store (review status tracking)."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SopStatus(str, Enum):
    """Review state of a single SOP extraction run."""
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class SopRecord(BaseModel):
    """One row of ``sop_records`` — a single extraction run of an SOP."""
    model_config = ConfigDict(populate_by_name=True)

    id: int
    job_id: str
    document_uid: str = Field(alias="document_Uid")
    document_number: Optional[str] = None
    document_name: Optional[str] = None
    document_title: Optional[str] = None
    document_version: Optional[str] = None
    document_type: Optional[str] = None
    file_type: str = ""
    language: str = "en"
    page_count: int = 0
    gpdat_version: int = 0
    status: SopStatus = SopStatus.APPROVED
    source_filename: Optional[str] = None
    output_path: Optional[str] = None
    created_at: str
    updated_at: str


class SopStatusUpdate(BaseModel):
    """Payload to change a record's review status."""
    status: SopStatus


class SopListResponse(BaseModel):
    """Paginated list of SOP records."""
    count: int
    records: list[SopRecord] = Field(default_factory=list)
