from datetime import datetime
from typing import Any, Literal, Optional

import re

from pydantic import BaseModel, Field, field_validator


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
    last_calculation_id: Optional[int] = None

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
    asutp_factors: Optional[dict[str, str]] = None  # Ф2→п.1.1, Ф5→п.2.2 etc. (СБЦП-22 only)
    asutp_k: float = 1.0                           # correction coefficient from СБЦП-22 table 3

    @field_validator('x_unit', 'sbts_code', 'section_name', mode='before')
    @classmethod
    def _coerce_str(cls, v):
        return "" if v is None else v

    @field_validator('sbts_table', mode='before')
    @classmethod
    def _parse_sbts_table(cls, v):
        if v is None or isinstance(v, int):
            return v
        if isinstance(v, str):
            m = re.search(r'\d+', v)
            return int(m.group()) if m else None
        return v

    @field_validator('quantity', mode='before')
    @classmethod
    def _coerce_quantity(cls, v):
        return 1 if v is None else v


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    stage: Literal["П", "Р", "П+Р"] = "П+Р"
    region: str = ""
    tz_object_name: str = ""   # formal object name from TZ header, e.g. «Система управления...»
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
    calc_method: str = "standard"
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


# ── ASUTP Admin ───────────────────────────────────────────────────────────────

class AsutpFactorOptionOut(BaseModel):
    id: int
    factor_code: str
    factor_name: str
    option_code: str
    option_description: str
    score_or: Optional[int]
    score_oo: Optional[int]
    score_io: Optional[int]
    score_to: Optional[int]
    score_mo: Optional[int]
    score_po: Optional[int]

    class Config:
        from_attributes = True


class AsutpFactorOptionIn(BaseModel):
    factor_code: str
    factor_name: str
    option_code: str
    option_description: str
    score_or: Optional[int] = None
    score_oo: Optional[int] = None
    score_io: Optional[int] = None
    score_to: Optional[int] = None
    score_mo: Optional[int] = None
    score_po: Optional[int] = None


class AsutpModuleOut(BaseModel):
    id: int
    module_code: str
    s_value: float
    sort_order: int
    stage_r_min: int
    stage_r_max: int
    stage_p_min: int
    stage_p_max: int

    class Config:
        from_attributes = True


class AsutpModulePatch(BaseModel):
    s_value: Optional[float] = None
    stage_r_min: Optional[int] = None
    stage_r_max: Optional[int] = None
    stage_p_min: Optional[int] = None
    stage_p_max: Optional[int] = None


# ── ИГИ (geological survey) ───────────────────────────────────────────────────

class IgiItem(BaseModel):
    """One line item in a geological survey estimate."""
    work_category: Literal["field", "lab", "kameral", "program"] = "field"
    object_type_name: str = ""          # display name, e.g. "Бурение колонковым способом"
    table_num: int
    row_num: str = ""
    description: str = ""
    volume: float
    a: float = 0                        # fixed cost component (ПЗ1п), руб at base year; 0 when not applicable
    x_unit: str = ""                    # unit label from reference_rows, e.g. "п.м"
    b: float                            # rate in rubles from reference_rows (at base year)
    deleted: bool = False
    notes: str = ""


class GeologicalSurvey(BaseModel):
    """One geological survey block attached to a calculation."""
    book_id: int                        # id of НЗ-2025-МС281-ИГИ (or any future НЗ)
    book_code: str = ""                 # e.g. "НЗ-2025-МС281-ИГИ"
    complexity_category: int = 2        # 1 | 2 | 3 (ИГИ conditions category)
    k1: float = 0.70                    # home-base coefficient (Table 1 НЗ)
    winter_pct: float = 0.0             # winter surcharge fraction, e.g. 0.29
    k2: float = 1.0                     # climate zone coefficient (Table 2 НЗ)
    items: list[IgiItem] = []
