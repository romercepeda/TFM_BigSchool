"""Pydantic schemas for D08 — Internationalization."""

from pydantic import BaseModel, Field


class LanguageUpdateRequest(BaseModel):
    language: str = Field(..., description="Language code to set (e.g. 'es', 'en').")


class LanguageUpdateResponse(BaseModel):
    preferred_language: str
