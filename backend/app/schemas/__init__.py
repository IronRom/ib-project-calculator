from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


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
    name: str  # matches coeff_key in book_conditions; unknown keys are silently skipped
    value: float = Field(default=1.0, ge=0.5, le=3.0)
    reason: str = ""


class ExtractedEntity(BaseModel):
    category: Literal["new_construction", "reconstruction", "overhaul"]
    object_type: str
    object_name: str
    address: str
    sbts_code: str = ""
    sbts_table: Optional[int] = None
    sbts_object_type_id: Optional[int] = None
    x_value: Optional[float] = None
    x_unit: str = ""
    quantity: int = 1
    coefficients: list[CoefficientInput] = []
    notes: Optional[str] = ""
    confidence: float = 0.0
    tz_quote: Optional[str] = ""         # verbatim excerpt from TZ that justifies this entity
    x_value_missing_reason: Optional[str] = None  # set when x_value=None after all passes
    deleted: bool = False                          # soft-delete by user on validation screen
    section_num: int = 0            # 0 = no explicit stage in TZ
    section_name: str = ""          # short stage name ≤60 chars, empty when section_num=0


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
    price_base_year: int = 2001
    pdf_filename: Optional[str]
    uploaded_at: datetime
    activated_at: Optional[datetime]
    notes: Optional[str]

    class Config:
        from_attributes = True


class ReferenceBookUpdate(BaseModel):
    notes: Optional[str] = None
    parse_prompt: Optional[str] = None
    price_base_year: Optional[int] = None


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


class PriceQuarterlyIndexCreate(BaseModel):
    year: int
    quarter: int
    base_year: int
    work_type: str = "project"
    index_value: float
    source_ref: str


class PriceQuarterlyIndexOut(BaseModel):
    id: int
    year: int
    quarter: int
    base_year: int
    work_type: str
    index_value: float
    source_ref: str

    class Config:
        from_attributes = True
