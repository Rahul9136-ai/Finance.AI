# Roles & Permissions (RBAC)

Permissions are fine-grained strings `resource:action` (e.g. `invoice:post`).
Roles bundle permissions. Users have exactly one role per org (ABAC in Phase 2).
The `require(*perms)` dependency guards every mutating route.

## Permission verbs

`read`, `create`, `update`, `post`, `approve`, `void`, `delete`, `export`, `admin`

## Resources

`dashboard, account, journal, invoice, payment, vendor, customer, tax, report,
user, ai`

## Role → permission matrix (Phase 1 subset)

| Role | Scope |
|---|---|
| **super_admin** | `*:*` — everything, all orgs |
| **cfo** / **finance_director** | read all; `journal:post`, `invoice:*`, `payment:*`, `report:*`, `ai:*`, `tax:*` |
| **finance_manager** | `journal:create/post`, `invoice:*`, `payment:create/approve`, `report:read/export`, `ai:read` |
| **accountant** | `journal:create`, `invoice:create/update/post`, `payment:create`, `vendor:*`, `customer:*`, `report:read`, `ai:read` |
| **auditor** | `*:read`, `report:export`, `journal:read` (no writes) |
| **ap_clerk** | `invoice:create/update` (AP), `vendor:read`, `payment:create` |
| **ar_clerk** | `invoice:create/update` (AR), `customer:*`, `payment:create` |
| **viewer** | `dashboard:read`, `report:read` |

## Enforcement

```python
@router.post("/journal", dependencies=[Depends(require("journal:post"))])
```

- `super_admin` short-circuits all checks.
- Every request resolves `current_user` (JWT) → `org_id` + `role` → permission
  set. Missing permission → HTTP 403 with an audit entry.
- All mutations are written to `audit_log` with actor, action, target, and diff.

## Seeded demo users

| Email | Password | Role |
|---|---|---|
| `admin@demo.io` | `demo1234` | super_admin |
| `cfo@demo.io` | `demo1234` | cfo |
| `manager@demo.io` | `demo1234` | finance_manager |
| `accountant@demo.io` | `demo1234` | accountant |
| `auditor@demo.io` | `demo1234` | auditor |
