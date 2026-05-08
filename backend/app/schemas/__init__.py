from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    company: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    can_calculate: bool
    company: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Projects ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str


class ProjectFileOut(BaseModel):
    id: int
    filename: str
    file_type: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: int
    name: str
    status: str
    created_at: datetime
    files: list[ProjectFileOut] = []

    class Config:
        from_attributes = True


# ── Calculations ──────────────────────────────────────────────────────────────

class CoefficientInput(BaseModel):
    name: str
    value: float
    source: str = ""


class ExtractedEntity(BaseModel):
    category: Literal["new_construction", "reconstruction", "overhaul"]
    object_type: str
    object_name: str
    address: str
    sbts_code: str = ""
    sbts_table: Optional[int] = None
    x_value: Optional[float] = None
    x_unit: str = ""
    coefficients: list[CoefficientInput] = []
    notes: str = ""
    confidence: float = 0.0


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    stage: Literal["П", "Р", "П+Р"] = "П+Р"
    region: str = ""
    missing_data: list[str] = []
    overall_confidence: float = 0.0


class CalculationOut(BaseModel):
    id: int
    project_id: int
    extracted_entities: Optional[Any]
    confirmed_positions: Optional[Any]
    calculation_result: Optional[Any]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Admin ─────────────────────────────────────────────────────────────────────

class UserUpdateAdmin(BaseModel):
    can_calculate: Optional[bool] = None
    role: Optional[str] = None


class ReferenceBookOut(BaseModel):
    id: int
    code: str
    official_name: str
    version: int
    status: str
    is_active: bool
    pdf_filename: Optional[str]
    uploaded_at: datetime
    activated_at: Optional[datetime]
    notes: Optional[str]

    class Config:
        from_attributes = True


class ReferenceBookUpdate(BaseModel):
    notes: Optional[str] = None
    parse_prompt: Optional[str] = None


class PriceIndexCreate(BaseModel):
    year: int
    quarter: int
    index_type: str = "project"
    index_value: float
    source_ref: str


class PriceIndexOut(BaseModel):
    id: int
    year: int
    quarter: int
    index_type: str
    index_value: float
    source_ref: str

    class Config:
        from_attributes = True
