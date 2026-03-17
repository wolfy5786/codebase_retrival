"""Pydantic schemas for ingestion endpoints."""
from pydantic import BaseModel


class IngestionJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
