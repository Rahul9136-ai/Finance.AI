from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Organization(Base):
    """Tenant. Every domain row is scoped by org_id."""

    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2), default="IN")
    base_currency: Mapped[str] = mapped_column(String(3), default="INR")
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
