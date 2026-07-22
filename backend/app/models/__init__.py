from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class PriceQuarterlyIndex(Base):
    """Per-base-year quarterly price indices from Минстрой letters.

    base_year: price level year of the reference book (2001, 2021, 2022, ...)
    work_type: 'project' | 'survey'
    index_value: multiplier from base_year level to current prices
    """
    __tablename__ = "price_quarterly_indices"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    base_year = Column(Integer, nullable=False)
    work_type = Column(String(20), nullable=False, default="project")
    index_value = Column(Numeric(10, 4), nullable=False)
    source_ref = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("year", "quarter", "base_year", "work_type", name="uq_quarterly_index"),
    )


class BookCondition(Base):
    """Coefficient conditions extracted from a reference book.

    table_num=None means the condition applies book-wide.
    row_range is a free-text descriptor, e.g. "п.1-9" or "п.13-21".
    effect_type: "multiplier_range" | "flag" | "additive"
    coeff_min/coeff_max: the coefficient value range (equal when exact).
    """
    __tablename__ = "book_conditions"

    id = Column(Integer, primary_key=True, index=True)
    book_version_id = Column(Integer, ForeignKey("reference_books.id"), nullable=False, index=True)
    table_num = Column(Integer, nullable=True, index=True)   # NULL = book-wide
    row_range = Column(String(50), nullable=True)            # "п.1-9", "п.13+", etc.
    condition_short = Column(Text, nullable=False)           # one-line description for AI context
    condition_text_full = Column(Text, nullable=True)        # verbatim from PDF
    effect_type = Column(String(30), nullable=False, default="multiplier_range")
    coeff_min = Column(Numeric(8, 4), nullable=True)
    coeff_max = Column(Numeric(8, 4), nullable=True)
    coeff_key = Column(String(30), nullable=True)            # "asu", "seismic", "reconstruction", etc.
    # How the coefficient combines: "multiply" (ценообразующий, перемножается) |
    # "additive" (усложняющий, 1+Σ(Ki−1) по МУ №620 п.3.14).
    # NULL → legacy behavior: режим определяется по имени ключа в calculator.
    apply_mode = Column(String(10), nullable=True)

    book = relationship("ReferenceBook")


class BookSectionShare(Base):
    """Распределение стоимости по разделам проектной/рабочей документации.

    Источник — таблицы «относительной стоимости разделов» самих СБЦ/НЗ.
    table_num=None — распределение действует на всю книгу; строка с конкретным
    table_num перекрывает книжное. stage: 'ПД' | 'РД'. pct — проценты (0-100),
    сумма всех разделов стадии = 100.
    """
    __tablename__ = "book_section_shares"

    id = Column(Integer, primary_key=True, index=True)
    book_version_id = Column(Integer, ForeignKey("reference_books.id"), nullable=False, index=True)
    table_num = Column(Integer, nullable=True, index=True)   # NULL = book-wide
    row_range = Column(String(50), nullable=True)
    stage = Column(String(2), nullable=False)                # 'ПД' | 'РД'
    section_code = Column(String(20), nullable=False)        # 'ПЗ', 'АР', 'ИОС.ЭС', ...
    section_name = Column(Text, nullable=False)
    pct = Column(Numeric(6, 3), nullable=False)              # 0-100

    book = relationship("ReferenceBook")


class BookExtractionHint(Base):
    """Domain-specific extraction rules per reference book.

    Stored in DB, managed by admins. Injected into pass-1 AI context.
    justification shown under the corresponding PIR entity in results.
    """
    __tablename__ = "book_extraction_hints"

    id = Column(Integer, primary_key=True, index=True)
    book_version_id = Column(Integer, ForeignKey("reference_books.id"), nullable=False, index=True)
    trigger_condition = Column(Text, nullable=False)  # "При наличии КНС (таблица 9)"
    implied_work = Column(Text, nullable=False)        # "Рассеивающий выпуск (таблица 14)"
    hint_for_ai = Column(Text, nullable=False)         # injected into AI context verbatim
    justification = Column(Text, nullable=False)       # shown under entity in results UI
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    book = relationship("ReferenceBook")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(10), nullable=False, default="user")
    can_calculate = Column(Boolean, nullable=False, default=False)
    company = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    projects = relationship("Project", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="projects")
    files = relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    calculations = relationship("Calculation", back_populates="project", cascade="all, delete-orphan")


class ProjectFile(Base):
    __tablename__ = "project_files"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(20), nullable=False, default="tz")
    extracted_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="files")


class ReferenceBook(Base):
    __tablename__ = "reference_books"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, index=True)
    official_name = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(30), nullable=False, default="requires_validation")
    is_active = Column(Boolean, nullable=False, default=False)
    price_base_year = Column(Integer, nullable=False, default=2001)
    calc_method = Column(String(20), nullable=False, default="standard")  # standard | asutp | survey
    # Методика ценообразования: 'mu620' (СБЦП) | '707pr' (НЗ) | 'mrr' (Москва).
    # Определяет режим экстраполяции в _match_row (миграция b8c9d0e1f2a3)
    pricing_method = Column(String(10), nullable=False, default="mu620")
    # Региональная привязка: NULL = федеральный; 'Москва и МО' — МРР
    region = Column(String(50), nullable=True)
    # Per-book П/Р distribution (fraction of base price). NULL → МУ №620 п.1.4 default (0.4/0.6).
    # НЗ книги задают своё распределение (например НЗ-847 табл.2.3: П=0.6, Р=0.4).
    pd_pct = Column(Numeric(4, 3), nullable=True)
    rd_pct = Column(Numeric(4, 3), nullable=True)
    parse_prompt = Column(Text, nullable=True)
    pdf_filename = Column(String(500), nullable=True)
    pdf_path = Column(String(1000), nullable=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    object_types = relationship("BookObjectType", back_populates="book", cascade="all, delete-orphan")
    rows = relationship("ReferenceRow", back_populates="book", cascade="all, delete-orphan")


class BookObjectType(Base):
    __tablename__ = "book_object_types"

    id = Column(Integer, primary_key=True, index=True)
    book_version_id = Column(Integer, ForeignKey("reference_books.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    table_num = Column(Integer, nullable=True)
    work_category = Column(String(20), nullable=True, default="field")
    notes = Column(Text, nullable=True)

    book = relationship("ReferenceBook", back_populates="object_types")
    rows = relationship("ReferenceRow", back_populates="object_type")


class ReferenceRow(Base):
    __tablename__ = "reference_rows"

    id = Column(Integer, primary_key=True, index=True)
    book_version_id = Column(Integer, ForeignKey("reference_books.id"), nullable=False, index=True)
    object_type_id = Column(Integer, ForeignKey("book_object_types.id"), nullable=True, index=True)
    table_num = Column(Integer, nullable=False, index=True)
    row_num = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    x_min = Column(Numeric(18, 4), nullable=True)
    x_max = Column(Numeric(18, 4), nullable=True)
    x_unit = Column(String(100), nullable=True)
    a = Column(Numeric(18, 4), nullable=True)
    b = Column(Numeric(18, 4), nullable=True)
    notes = Column(Text, nullable=True)

    book = relationship("ReferenceBook", back_populates="rows")
    object_type = relationship("BookObjectType", back_populates="rows")


class PriceIndex(Base):
    __tablename__ = "price_indices"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    index_type = Column(String(20), nullable=False, default="project")
    index_value = Column(Numeric(10, 4), nullable=False)
    source_ref = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("year", "quarter", "index_type", name="uq_price_index"),
    )


class Calculation(Base):
    __tablename__ = "calculations"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    book_version_id = Column(Integer, ForeignKey("reference_books.id"), nullable=True)
    price_index_id = Column(Integer, ForeignKey("price_indices.id"), nullable=True)
    extracted_entities = Column(JSONB, nullable=True)
    confirmed_positions = Column(JSONB, nullable=True)
    calculation_result = Column(JSONB, nullable=True)
    normative_citations = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="calculations")
    book = relationship("ReferenceBook")
    price_index = relationship("PriceIndex")


class AsutpFactorOption(Base):
    """Factor score options for ASUTP calculation (СБЦП-2001-22 Table 2).

    factor_code: 'Ф2', 'Ф5', 'Ф6', 'Ф7', 'Ф8', 'Ф9', 'Ф10'
    option_code: 'п.1.1', 'п.2.2', ... (section.row in Table 2)
    score_*: ball score per module column (ОР, ОО, ИО, ТО, МО, ПО)
    """
    __tablename__ = "asutp_factor_options"

    id = Column(Integer, primary_key=True, index=True)
    book_version_id = Column(Integer, ForeignKey("reference_books.id"), nullable=False, index=True)
    factor_code = Column(String(5), nullable=False)
    factor_name = Column(Text, nullable=False)
    option_code = Column(String(20), nullable=False)
    option_description = Column(Text, nullable=False)
    score_or = Column(Integer, nullable=True)
    score_oo = Column(Integer, nullable=True)
    score_io = Column(Integer, nullable=True)
    score_to = Column(Integer, nullable=True)
    score_mo = Column(Integer, nullable=True)
    score_po = Column(Integer, nullable=True)

    book = relationship("ReferenceBook")


class AsutpModule(Base):
    """Module definitions for ASUTP calculation: S value + stage percentages per module.

    module_code: 'ОР', 'ОО', 'ИО', 'ТО', 'МО', 'ПО'
    s_value: cost multiplier тыс.руб. (from СБЦП-2001-22 п.2.11.2)
    stage_r_min/max: allowed % range for Р (рабочая) stadia
    stage_p_min/max: allowed % range for П (проектная) stadia
    """
    __tablename__ = "asutp_modules"

    id = Column(Integer, primary_key=True, index=True)
    book_version_id = Column(Integer, ForeignKey("reference_books.id"), nullable=False, index=True)
    module_code = Column(String(5), nullable=False)
    s_value = Column(Numeric(10, 2), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    stage_r_min = Column(Integer, nullable=False, default=0)
    stage_r_max = Column(Integer, nullable=False, default=100)
    stage_p_min = Column(Integer, nullable=False, default=0)
    stage_p_max = Column(Integer, nullable=False, default=100)

    book = relationship("ReferenceBook")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(Integer, nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")
