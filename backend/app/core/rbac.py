from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User


def _has_permission(perms: set[str], needed: str) -> bool:
    if "*:*" in perms or needed in perms:
        return True
    resource, action = needed.split(":", 1)
    # Wildcards: "invoice:*" or "*:read"
    return f"{resource}:*" in perms or f"*:{action}" in perms


def require(*needed: str):
    """Dependency factory: user must hold ALL listed permissions."""

    def checker(user: User = Depends(get_current_user)) -> User:
        perms = user.role.perm_set()
        missing = [n for n in needed if not _has_permission(perms, n)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission(s): {', '.join(missing)}",
            )
        return user

    return checker
