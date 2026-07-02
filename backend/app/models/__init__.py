"""
SQLAlchemy ORM models for the VN Accounting platform.
All monetary values stored in VND (integer, no decimals).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, PyEnum):
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"


class DocumentStatus(str, PyEnum):
    PENDING = "pending"           # uploaded, awaiting OCR
    PROCESSING = "processing"     # OCR job running
    EXTRACTED = "extracted"       # fields extracted, needs review
    VERIFIED = "verified"         # human confirmed
    REJECTED = "rejected"         # invalid / duplicate
    FAILED = "failed"             # processing exhausted retries or hit fatal error


class DocumentType(str, PyEnum):
    INVOICE_VAT = "invoice_vat"           # Hóa đơn GTGT
    INVOICE_SALE = "invoice_sale"         # Hóa đơn bán hàng
    RECEIPT = "receipt"                   # Phiếu thu/chi
    CONTRACT = "contract"                 # Hợp đồng
    BANK_STATEMENT = "bank_statement"
    OTHER = "other"


class VATRate(str, PyEnum):
    ZERO = "0"
    FIVE = "5"
    EIGHT = "8"
    TEN = "10"
    EXEMPT = "exempt"
    NOT_APPLICABLE = "na"


class JournalEntryStatus(str, PyEnum):
    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"


class TaxDeclarationPeriod(str, PyEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class DirectionStatus(str, PyEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.ACCOUNTANT
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id"), nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="users")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="uploaded_by")


class Company(TimestampMixin, Base):
    """A Vietnamese legal entity (doanh nghiệp)."""
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(500))
    tax_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)  # MST
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    # VAS (Vietnam Accounting Standards) or IFRS
    accounting_standard: Mapped[str] = mapped_column(String(10), default="VAS")
    # monthly or quarterly VAT filing
    vat_declaration_period: Mapped[TaxDeclarationPeriod] = mapped_column(
        Enum(TaxDeclarationPeriod, values_callable=lambda x: [e.value for e in x]),
        default=TaxDeclarationPeriod.QUARTERLY
    )
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    users: Mapped[list["User"]] = relationship("User", back_populates="company")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="company")
    journal_entries: Mapped[list["JournalEntry"]] = relationship("JournalEntry", back_populates="company")


class Document(TimestampMixin, Base):
    """Raw uploaded document (invoice image, PDF, etc.)."""
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    uploaded_by_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    # Storage
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)   # R2 URL
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    mime_type: Mapped[str] = mapped_column(String(100), default="image/jpeg")
    file_checksum: Mapped[str | None] = mapped_column(String(64), index=True)

    # Classification
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, values_callable=lambda x: [e.value for e in x]),
        default=DocumentType.OTHER
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, values_callable=lambda x: [e.value for e in x]),
        default=DocumentStatus.PENDING
    )
    duplicate_of_document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("documents.id"), nullable=True)

    # OCR results (raw) — backwards-compatible merged text
    ocr_raw_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    # Extended OCR metadata (queryable)
    ocr_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)          # "google" | "paddle" | "mock"
    ocr_engine_version: Mapped[str | None] = mapped_column(String(50), nullable=True)    # engine version string
    ocr_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)         # total OCR wall-clock ms
    ocr_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)           # pages processed
    ocr_language: Mapped[str | None] = mapped_column(String(20), nullable=True)          # language hints used
    ocr_warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)               # non-fatal warnings
    ocr_pages: Mapped[list | None] = mapped_column(JSONB, nullable=True)                 # per-page breakdown

    # Extracted structured data (from Claude)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)
    extraction_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))

    # Processing job reference
    celery_job_id: Mapped[str | None] = mapped_column(String(255))
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error: Mapped[str | None] = mapped_column(Text)

    company: Mapped["Company"] = relationship("Company", back_populates="documents")
    uploaded_by: Mapped["User"] = relationship("User", back_populates="documents")
    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="document", uselist=False)


class Invoice(TimestampMixin, Base):
    """
    Structured invoice data extracted from a Document.
    Follows Vietnamese invoice standard (Nghị định 123/2020).
    """
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), unique=True, nullable=False)

    # Invoice identity
    invoice_series: Mapped[str | None] = mapped_column(String(20))   # Ký hiệu (e.g. "AA/23E")
    invoice_number: Mapped[str | None] = mapped_column(String(50))   # Số hóa đơn

    # Invoice direction (H-5): "inbound" or "outbound"
    invoice_direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    direction_status: Mapped[DirectionStatus] = mapped_column(
        Enum(DirectionStatus, values_callable=lambda x: [e.value for e in x]),
        default=DirectionStatus.UNKNOWN,
        nullable=False,
    )
    direction_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)

    # Currency conversion (M-8)
    exchange_rate: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    exchange_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    converted_vnd_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    invoice_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invoice_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, values_callable=lambda x: [e.value for e in x]),
        default=DocumentType.INVOICE_VAT
    )

    # Seller info
    seller_name: Mapped[str | None] = mapped_column(String(500))
    seller_tax_code: Mapped[str | None] = mapped_column(String(20))  # MST người bán
    seller_address: Mapped[str | None] = mapped_column(Text)
    seller_bank_account: Mapped[str | None] = mapped_column(String(50))

    # Buyer info
    buyer_name: Mapped[str | None] = mapped_column(String(500))
    buyer_tax_code: Mapped[str | None] = mapped_column(String(20))   # MST người mua
    buyer_address: Mapped[str | None] = mapped_column(Text)

    # Amounts (in VND, no decimal)
    currency_code: Mapped[str] = mapped_column(String(3), default="VND")  # ISO 4217; VND is default; non-VND invoices must be converted
    subtotal_amount: Mapped[int] = mapped_column(BigInteger, default=0)    # Cộng tiền hàng
    vat_rate: Mapped[VATRate] = mapped_column(
        Enum(VATRate, values_callable=lambda x: [e.value for e in x]),
        default=VATRate.TEN
    )
    vat_amount: Mapped[int] = mapped_column(BigInteger, default=0)         # Tiền thuế GTGT
    total_amount: Mapped[int] = mapped_column(BigInteger, default=0)       # Tổng tiền thanh toán

    # e-Invoice fields
    einvoice_code: Mapped[str | None] = mapped_column(String(100))  # Mã CQT
    einvoice_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    einvoice_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    einvoice_verification_data: Mapped[dict | None] = mapped_column(JSONB)  # H-5: full GDT response

    # Line items stored as JSONB
    line_items: Mapped[list | None] = mapped_column(JSONB)
    # [{name, unit, quantity, unit_price, amount, vat_rate}]

    # Notes
    notes: Mapped[str | None] = mapped_column(Text)
    # Extraction quality (synced from Document.extraction_confidence after processing)
    extraction_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))

    # Direction fields (H-5): populated by track-e during direction classification
    invoice_direction: Mapped[str | None] = mapped_column(String(20))       # "sale" | "purchase" | None
    direction_status: Mapped[str] = mapped_column(String(20), default="unknown")  # "unknown" | "pending_review" | "confirmed"
    direction_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))   # 0.0–1.0

    document: Mapped["Document"] = relationship("Document", back_populates="invoice")
    journal_entries: Mapped[list["JournalEntry"]] = relationship("JournalEntry", back_populates="invoice")


class ChartOfAccount(TimestampMixin, Base):
    """
    Vietnam chart of accounts (Hệ thống tài khoản kế toán).
    Circular 200/2014 and Circular 133/2016.
    """
    __tablename__ = "chart_of_accounts"
    __table_args__ = (UniqueConstraint("company_id", "account_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    account_code: Mapped[str] = mapped_column(String(20), nullable=False)    # e.g. "1111", "33311"
    account_name: Mapped[str] = mapped_column(String(500), nullable=False)
    account_name_en: Mapped[str | None] = mapped_column(String(500))
    parent_code: Mapped[str | None] = mapped_column(String(20))
    account_type: Mapped[str] = mapped_column(String(50))  # asset/liability/equity/revenue/expense
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # seeded from standard

    debit_lines: Mapped[list["JournalEntryLine"]] = relationship(
        "JournalEntryLine", foreign_keys="JournalEntryLine.debit_account_code",
        primaryjoin="ChartOfAccount.account_code == JournalEntryLine.debit_account_code",
        back_populates="debit_account"
    )


class JournalEntry(TimestampMixin, Base):
    """
    Accounting journal entry (Bút toán).
    """
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("invoices.id"), nullable=True)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JournalEntryStatus] = mapped_column(
        Enum(JournalEntryStatus, values_callable=lambda x: [e.value for e in x]),
        default=JournalEntryStatus.DRAFT
    )
    total_amount: Mapped[int] = mapped_column(BigInteger, default=0)

    company: Mapped["Company"] = relationship("Company", back_populates="journal_entries")
    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="journal_entries")
    lines: Mapped[list["JournalEntryLine"]] = relationship(
        "JournalEntryLine", back_populates="journal_entry", cascade="all, delete-orphan"
    )


class JournalEntryLine(TimestampMixin, Base):
    """A single debit/credit line in a journal entry."""
    __tablename__ = "journal_entry_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    journal_entry_id: Mapped[str] = mapped_column(String(36), ForeignKey("journal_entries.id"), nullable=False)
    debit_account_code: Mapped[str | None] = mapped_column(String(20))
    credit_account_code: Mapped[str | None] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    journal_entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    debit_account: Mapped["ChartOfAccount | None"] = relationship(
        "ChartOfAccount",
        foreign_keys=[debit_account_code],
        primaryjoin="JournalEntryLine.debit_account_code == ChartOfAccount.account_code",
        back_populates="debit_lines"
    )
