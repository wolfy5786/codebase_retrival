"""Pydantic schemas for auth endpoints."""
from pydantic import BaseModel


class UserMeResponse(BaseModel):
    id: str
    email: str
    app_metadata: dict

