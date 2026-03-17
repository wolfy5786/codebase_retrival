"""Pydantic schemas for admin user endpoints."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AdminUserCreate(BaseModel):
    email: str = Field(..., pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(..., min_length=6)
    role: str = Field(..., pattern="^(admin|user)$")


class AdminUserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|user)$")


class AdminUserResponse(BaseModel):
    id: UUID
    email: str | None
    app_metadata: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True
