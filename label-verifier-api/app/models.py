from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field, field_validator


class FieldStatus(StrEnum):
    MATCH = "match"
    REVIEW = "review"
    MISMATCH = "mismatch"
    MISSING = "missing"


class ApplicationData(BaseModel):
    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str
    country_of_origin: str | None = None

    @field_validator("brand_name", "class_type", "alcohol_content", "net_contents")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field is required.")
        return value.strip()


class FieldResult(BaseModel):
    field: str
    expected: str
    observed: str | None
    status: FieldStatus
    reason: str
    evidence: list[str] = Field(default_factory=list)
    similarity: float | None = None


class AnalysisResult(BaseModel):
    overall_status: FieldStatus
    processing_ms: int
    ocr_text: str
    fields: list[FieldResult]
    limitations: list[str]
