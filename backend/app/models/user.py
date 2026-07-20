from sqlalchemy import ForeignKey, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(Base):
    __tablename__ = "role"

    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    # Comma-separated "resource:action" permissions. "*:*" == superuser.
    permissions: Mapped[str] = mapped_column(Text, default="")

    def perm_set(self) -> set[str]:
        return {p.strip() for p in self.permissions.split(",") if p.strip()}


class User(Base):
    __tablename__ = "user"

    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    role: Mapped["Role"] = relationship(lazy="joined")
