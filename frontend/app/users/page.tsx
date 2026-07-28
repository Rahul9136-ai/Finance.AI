"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";
import { downloadCsv, toCsv } from "@/lib/csv";
import { Check, Copy, Download, Pencil, Plus, Power, ShieldPlus, Trash2, UserPlus, X } from "lucide-react";

type UserRow = {
  id: number; email: string; full_name: string; role: string;
  is_active: boolean; must_change_password: boolean;
};
type RoleRow = { id: number; name: string; description: string; permissions: string[] };
type PermissionEntry = { resource: string; label: string; actions: string[] };

const PROTECTED_ROLE = "super_admin";

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [catalog, setCatalog] = useState<PermissionEntry[]>([]);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("");
  const [err, setErr] = useState("");
  const [forbidden, setForbidden] = useState(false);
  const [creating, setCreating] = useState(false);
  const [tempCred, setTempCred] = useState<{ email: string; password: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [roleModal, setRoleModal] = useState<{ role: RoleRow | null } | null>(null);
  const [meId, setMeId] = useState<number | null>(null);

  function load() {
    api.get("/api/users").then(setUsers).catch((e) => {
      if (String(e.message).includes("403")) setForbidden(true);
    });
    api.get("/api/roles").then((r: RoleRow[]) => {
      setRoles(r);
      setRole((cur) => cur || r[0]?.name || "");
    }).catch(() => {});
    api.get("/api/permissions").then(setCatalog).catch(() => {});
    api.get("/api/auth/me").then((m) => setMeId(m.id)).catch(() => {});
  }
  useEffect(load, []);

  async function toggleActive(u: UserRow) {
    const verb = u.is_active ? "deactivate" : "reactivate";
    if (!confirm(`${verb === "deactivate" ? "Deactivate" : "Reactivate"} ${u.full_name}?`)) return;
    try {
      await api.patch(`/api/users/${u.id}`, { is_active: !u.is_active });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setCreating(true);
    try {
      const r = await api.post("/api/users", { email, full_name: fullName, role });
      setTempCred({ email: r.email, password: r.temp_password });
      setEmail("");
      setFullName("");
      load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function deleteRole(r: RoleRow) {
    if (!confirm(`Delete role "${r.name}"? This only works if no one is assigned to it.`)) return;
    try {
      await api.del(`/api/roles/${r.id}`);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  function exportCsv() {
    const cols = ["full_name", "email", "role", "is_active", "must_change_password"];
    downloadCsv(`users-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(users, cols));
  }

  function copyPassword() {
    if (!tempCred) return;
    navigator.clipboard.writeText(tempCred.password);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (forbidden) {
    return (
      <Shell>
        <div className="card">
          <p className="text-sm">You don't have permission to manage users.</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1 className="mb-1 text-2xl font-bold">Users</h1>
      <p className="muted mb-5 text-sm">
        Add people to your org with a one-time temporary password. They'll be required
        to set their own password on first login.
      </p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 flex items-center gap-2 font-semibold">
            <UserPlus size={18} className="text-brand-500" /> Add person
          </h3>
          <form onSubmit={submit} className="space-y-3">
            <div>
              <label className="muted text-xs">Full name</label>
              <input className="input" value={fullName}
                onChange={(e) => setFullName(e.target.value)} required />
            </div>
            <div>
              <label className="muted text-xs">Email</label>
              <input className="input" type="email" value={email}
                onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div>
              <label className="muted text-xs">Role</label>
              <select className="input" value={role} onChange={(e) => setRole(e.target.value)}>
                {roles.map((r) => (
                  <option key={r.id} value={r.name}>{r.name}</option>
                ))}
              </select>
            </div>
            {err && <p className="text-sm text-red-500">{err}</p>}
            <button className="btn-primary" disabled={creating}>
              {creating ? "Creating…" : "Create user"}
            </button>
          </form>

          {tempCred && (
            <div className="mt-4 rounded-xl border p-3 text-sm" style={{ borderColor: "var(--border)" }}>
              <p className="mb-2">
                Temporary password for <span className="font-semibold">{tempCred.email}</span> —
                shown once, share it securely:
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded-lg bg-black/5 px-2 py-1 font-mono dark:bg-white/10">
                  {tempCred.password}
                </code>
                <button type="button" className="btn-ghost" onClick={copyPassword}>
                  {copied ? <Check size={16} /> : <Copy size={16} />}
                </button>
              </div>
              <p className="muted mt-2 text-xs">
                They'll be required to set their own password on first login.
              </p>
            </div>
          )}
        </div>

        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">Team</h3>
            <button className="btn-ghost" onClick={exportCsv} disabled={users.length === 0}>
              <Download size={16} /> Export CSV
            </button>
          </div>
          <div className="space-y-2">
            {users.map((u) => (
              <div key={u.id}
                className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"
                style={{ borderColor: "var(--border)" }}>
                <div>
                  <p className="font-medium">{u.full_name}</p>
                  <p className="muted text-xs">{u.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="badge bg-brand-100 text-brand-700">{u.role}</span>
                  {u.must_change_password && (
                    <span className="badge bg-amber-100 text-amber-700">Pending first login</span>
                  )}
                  {!u.is_active && <span className="badge bg-rose-100 text-rose-700">Inactive</span>}
                  {u.id !== meId && (
                    <button className="btn-ghost" onClick={() => toggleActive(u)}
                      title={u.is_active ? "Deactivate (revoke access)" : "Reactivate"}>
                      <Power size={14} className={u.is_active ? "text-rose-500" : "text-emerald-500"} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card mt-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 font-semibold">
            <ShieldPlus size={18} className="text-brand-500" /> Roles
          </h3>
          <button className="btn-primary" onClick={() => setRoleModal({ role: null })}>
            <Plus size={16} /> New role
          </button>
        </div>
        <p className="muted mb-3 text-xs">
          Give a role exactly the access it needs — only permissions that actually gate
          something in the app can be assigned.
        </p>
        <div className="space-y-2">
          {roles.map((r) => {
            const protectedRole = r.name === PROTECTED_ROLE;
            return (
              <div key={r.id} className="rounded-lg border px-3 py-2 text-sm"
                style={{ borderColor: "var(--border)" }}>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium">{r.name}</span>
                    {r.description && <span className="muted ml-2 text-xs">{r.description}</span>}
                  </div>
                  <div className="flex items-center gap-1">
                    {protectedRole ? (
                      <span className="badge bg-slate-200 text-slate-600">built-in, protected</span>
                    ) : (
                      <>
                        <button className="btn-ghost" onClick={() => setRoleModal({ role: r })}
                          title="Edit permissions">
                          <Pencil size={14} />
                        </button>
                        <button className="btn-ghost" onClick={() => deleteRole(r)} title="Delete role">
                          <Trash2 size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {r.permissions.includes("*:*") ? (
                    <span className="badge bg-violet-100 text-violet-700">all permissions</span>
                  ) : (
                    r.permissions.map((p) => (
                      <span key={p} className="badge border" style={{ borderColor: "var(--border)" }}>{p}</span>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {roleModal && (
        <RoleModal
          role={roleModal.role}
          catalog={catalog}
          onClose={() => setRoleModal(null)}
          onSaved={() => { setRoleModal(null); load(); }}
        />
      )}
    </Shell>
  );
}

function RoleModal({
  role, catalog, onClose, onSaved,
}: { role: RoleRow | null; catalog: PermissionEntry[]; onClose: () => void; onSaved: () => void }) {
  const isEdit = !!role;
  const [name, setName] = useState(role?.name || "");
  const [description, setDescription] = useState(role?.description || "");
  const [perms, setPerms] = useState<Set<string>>(new Set(role?.permissions || []));
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function toggle(perm: string) {
    setPerms((cur) => {
      const next = new Set(cur);
      if (next.has(perm)) next.delete(perm);
      else next.add(perm);
      return next;
    });
  }

  async function submit() {
    setErr("");
    if (!isEdit && !/^[a-z][a-z0-9_]*$/.test(name)) {
      setErr("Role name must be lowercase letters, numbers, or underscores, starting with a letter.");
      return;
    }
    setBusy(true);
    try {
      if (isEdit) {
        await api.patch(`/api/roles/${role!.id}`, { description, permissions: Array.from(perms) });
      } else {
        await api.post("/api/roles", { name, description, permissions: Array.from(perms) });
      }
      onSaved();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4"
      onClick={onClose}>
      <div className="card mt-10 w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">{isEdit ? `Edit role: ${role!.name}` : "New role"}</h3>
          <button className="btn-ghost" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="muted text-xs">Role name</label>
            <input className="input" value={name} disabled={isEdit}
              placeholder="e.g. ap_clerk_custom"
              onChange={(e) => setName(e.target.value.toLowerCase())} />
          </div>
          <div>
            <label className="muted text-xs">Description</label>
            <input className="input" value={description}
              onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>

        <label className="muted text-xs">Permissions</label>
        <div className="mt-1 space-y-2">
          {catalog.map((entry) => (
            <div key={entry.resource} className="rounded-lg border p-2" style={{ borderColor: "var(--border)" }}>
              <p className="mb-1 text-xs font-semibold">{entry.label}</p>
              <div className="flex flex-wrap gap-3">
                {entry.actions.map((action) => {
                  const key = `${entry.resource}:${action}`;
                  return (
                    <label key={key} className="flex items-center gap-1.5 text-sm">
                      <input type="checkbox" checked={perms.has(key)} onChange={() => toggle(key)} />
                      {action}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {err && <p className="mt-3 text-sm text-red-500">{err}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={busy || !name}>
            {busy ? "Saving…" : isEdit ? "Save changes" : "Create role"}
          </button>
        </div>
      </div>
    </div>
  );
}
