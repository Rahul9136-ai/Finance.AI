from sqlalchemy import ForeignKey, String, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Vendor(Base):
    __tablename__ = "vendor"

    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 2-digit GST state code; auto-derived from gstin when unset — only needs
    # setting explicitly for an unregistered vendor with no GSTIN.
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # AI-maintained trust score 0-100 (payment reliability, dupe history, etc.)
    ai_score: Mapped[float] = mapped_column(Numeric(5, 2), default=50)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    __tablename__ = "customer"

    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 2-digit GST state code; auto-derived from gstin when unset — only needs
    # setting explicitly for an unregistered/B2C customer with no GSTIN.
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    credit_limit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    # AI-predicted probability of default 0-1
    ai_default_risk: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
