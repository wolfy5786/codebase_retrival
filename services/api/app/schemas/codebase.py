"""Pydantic schemas for codebase endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CodebaseCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None


class CodebaseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1)
    description: str | None = None


class CodebaseResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CodebaseVersionResponse(BaseModel):
    id: UUID
    codebase_id: UUID
    version: int
    upload_source: str
    files_added: int
    files_modified: int
    files_deleted: int
    files_unchanged: int
    created_at: datetime

    class Config:
        from_attributes = True


class CodebaseDetailResponse(CodebaseResponse):
    versions: list[CodebaseVersionResponse] = []


class CodebaseListResponse(BaseModel):
    codebases: list[CodebaseResponse]
