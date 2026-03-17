"""Pydantic schemas for query endpoints."""
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    explain: bool = False


class QueryStubResponse(BaseModel):
    status: str
    message: str
    query: str
    explain: bool
