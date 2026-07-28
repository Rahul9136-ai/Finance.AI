from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User

# The full catalog of resource:action permissions actually enforced by a
# `require(...)` call somewhere in the API, plus role-management itself.
# This drives the custom-role permission picker — every entry here does
# something real; there's no "resource:action" a role could be given that
# isn't already checked by some route.
PERMISSION_CATALOG: list[dict] = [
    {"resource": "dashboard", "label": "Dashboard", "actions": ["read"]},
    {"resource": "account", "label": "Chart of Accounts", "actions": ["read"]},
    {"resource": "journal", "label": "General Ledger", "actions": ["read", "post"]},
    {"resource": "invoice", "label": "Invoices (AR/AP)", "actions": ["read", "create", "post"]},
    {"resource": "payment", "label": "Payments", "actions": ["create"]},
    {"resource": "vendor", "label": "Vendors", "actions": ["read", "create"]},
    {"resource": "customer", "label": "Customers", "actions": ["read", "create"]},
    {"resource": "report", "label": "Reports & Statements", "actions": ["read"]},
    {"resource": "user", "label": "User Management", "actions": ["read", "create", "update"]},
    {"resource": "role", "label": "Role Management", "actions": ["read", "create", "update"]},
    {"resource": "ai", "label": "AI Assistant", "actions": ["read"]},
]


def valid_permission_set() -> set[str]:
    return {f"{r['resource']}:{a}" for r in PERMISSION_CATALOG for a in r["actions"]}


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
