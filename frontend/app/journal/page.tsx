"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, inr } from "@/lib/api";
import { BookOpen, Scale, ListTree, Plus, Trash2, X } from "lucide-react";

type Line = { account_id: number; debit: number; credit: number; description: string };
type Entry = {
  id: number; ref: string; entry_date: string; memo: string;
  status: string; source: string; lines: Line[];
};

const statusTone: Record<string, string> = {
  posted: "bg-emerald-100 text-emerald-700",
  reversed: "bg-slate-200 text-slate-600",
  partial: "bg-amber-100 text-amber-700",
  draft: "bg-amber-100 text-amber-700",
};

type Tab = "journal" | "trial" | "ledger";
const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: "journal", label: "Journal Entries", icon: BookOpen },
  { id: "trial", label: "Trial Balance", icon: Scale },
  { id: "ledger", label: "Account Ledger", icon: ListTree },
];

export default function GeneralLedgerPage() {
  const [tab, setTab] = useState<Tab>("journal");
  const [accounts, setAccounts] = useState<any[]>([]);
  const [acctMap, setAcctMap] = useState<Record<number, string>>({});

  useEffect(() => {
    api.get("/api/accounts").then((a: any[]) => {
      setAccounts(a);
      setAcctMap(Object.fromEntries(a.map((x) => [x.id, `${x.code} ${x.name}`])));
    }).catch(() => {});
  }, []);

  return (
    <Shell>
      <h1 className="mb-1 text-2xl font-bold">General Ledger</h1>
      <p className="muted mb-4 text-sm">
        Double-entry validated. Posted entries are immutable — corrections are reversing entries.
      </p>

      <div className="mb-5 flex gap-1 rounded-xl border p-1" style={{ borderColor: "var(--border)", width: "fit-content" }}>
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`btn ${tab === t.id ? "bg-brand-600 text-white" : ""}`}>
              <Icon size={16} /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "journal" && <JournalTab acctMap={acctMap} accounts={accounts} />}
      {tab === "trial" && <TrialBalanceTab />}
      {tab === "ledger" && <AccountLedgerTab accounts={accounts} />}
    </Shell>
  );
}

function JournalTab({ acctMap, accounts }: { acctMap: Record<number, string>; accounts: any[] }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [showNew, setShowNew] = useState(false);
  const load = () => api.get("/api/journal").then(setEntries).catch(() => {});
  // Note: pass a block-body effect so it returns undefined (not the Promise from
  // `load`) — React would otherwise call the Promise as a cleanup fn on unmount.
  useEffect(() => { load(); }, []);

  async function reverse(id: number) {
    try { await api.post(`/api/journal/${id}/reverse`); load(); }
    catch (e: any) { alert(e.message); }
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button className="btn-primary" onClick={() => setShowNew(true)}>
          <Plus size={16} /> New Journal Entry
        </button>
      </div>
      {showNew && (
        <NewEntryModal
          accounts={accounts}
          onClose={() => setShowNew(false)}
          onPosted={() => { setShowNew(false); load(); }}
        />
      )}
      {entries.map((e) => {
        const total = e.lines.reduce((s, l) => s + Number(l.debit), 0);
        return (
          <div key={e.id} className="card">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-semibold">#{e.id}</span>{" "}
                <span className="muted text-sm">{e.entry_date}</span>{" "}
                <span className={`badge ${statusTone[e.status] || ""}`}>{e.status}</span>{" "}
                <span className="badge border" style={{ borderColor: "var(--border)" }}>{e.source}</span>
                <p className="text-sm">{e.memo}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-semibold">{inr(total)}</span>
                {e.status === "posted" && (
                  <button className="btn-ghost" onClick={() => reverse(e.id)}>Reverse</button>
                )}
              </div>
            </div>
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="muted text-left text-xs">
                  <th className="pb-1">Account</th>
                  <th className="pb-1 text-right">Debit</th>
                  <th className="pb-1 text-right">Credit</th>
                </tr>
              </thead>
              <tbody>
                {e.lines.map((l, i) => (
                  <tr key={i}>
                    <td className="py-0.5">{acctMap[l.account_id] || l.account_id}</td>
                    <td className="py-0.5 text-right">{Number(l.debit) ? inr(Number(l.debit)) : "—"}</td>
                    <td className="py-0.5 text-right">{Number(l.credit) ? inr(Number(l.credit)) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
      {entries.length === 0 && <p className="muted">No journal entries yet.</p>}
    </div>
  );
}

function TrialBalanceTab() {
  const [tb, setTb] = useState<any>(null);
  useEffect(() => { api.get("/api/ledger/trial-balance").then(setTb).catch(() => {}); }, []);
  if (!tb) return <p className="muted">Loading…</p>;

  return (
    <div className="card overflow-x-auto">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">Trial Balance</h3>
        <span className={`badge ${tb.balanced ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
          {tb.balanced ? "✓ Balanced" : "✗ Out of balance"}
        </span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="muted border-b text-left text-xs" style={{ borderColor: "var(--border)" }}>
            <th className="p-2">Code</th>
            <th className="p-2">Account</th>
            <th className="p-2">Type</th>
            <th className="p-2 text-right">Debit</th>
            <th className="p-2 text-right">Credit</th>
          </tr>
        </thead>
        <tbody>
          {tb.accounts.map((a: any) => (
            <tr key={a.account_id} className="border-b" style={{ borderColor: "var(--border)" }}>
              <td className="p-2 font-mono">{a.code}</td>
              <td className="p-2">{a.name}</td>
              <td className="p-2"><span className="badge border" style={{ borderColor: "var(--border)" }}>{a.type}</span></td>
              <td className="p-2 text-right">{a.debit ? inr(a.debit) : "—"}</td>
              <td className="p-2 text-right">{a.credit ? inr(a.credit) : "—"}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="font-bold">
            <td className="p-2" colSpan={3}>Total</td>
            <td className="p-2 text-right">{inr(tb.total_debit)}</td>
            <td className="p-2 text-right">{inr(tb.total_credit)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function AccountLedgerTab({ accounts }: { accounts: any[] }) {
  const [accountId, setAccountId] = useState<number | null>(null);
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const postable = accounts.filter((a) => a.is_postable);
    if (postable.length && accountId === null) setAccountId(postable[0].id);
  }, [accounts, accountId]);

  useEffect(() => {
    if (accountId != null) api.get(`/api/ledger/account/${accountId}`).then(setData).catch(() => {});
  }, [accountId]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <label className="muted text-sm">Account</label>
        <select className="input max-w-md" value={accountId ?? ""}
          onChange={(e) => setAccountId(Number(e.target.value))}>
          {accounts.filter((a) => a.is_postable).map((a) => (
            <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
          ))}
        </select>
      </div>

      {data && (
        <div className="card overflow-x-auto">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">{data.account.code} {data.account.name}</h3>
            <span className="text-sm">
              <span className="muted">Closing balance: </span>
              <span className="font-bold">{inr(data.closing_balance)}</span>
              <span className="muted"> ({data.account.normal})</span>
            </span>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="muted border-b text-left text-xs" style={{ borderColor: "var(--border)" }}>
                <th className="p-2">Date</th>
                <th className="p-2">Ref</th>
                <th className="p-2">Narration</th>
                <th className="p-2 text-right">Debit</th>
                <th className="p-2 text-right">Credit</th>
                <th className="p-2 text-right">Balance</th>
              </tr>
            </thead>
            <tbody>
              {data.lines.map((l: any, i: number) => (
                <tr key={i} className="border-b" style={{ borderColor: "var(--border)" }}>
                  <td className="p-2">{l.date}</td>
                  <td className="p-2 font-mono text-xs">{l.ref}</td>
                  <td className="p-2">{l.memo}</td>
                  <td className="p-2 text-right">{l.debit ? inr(l.debit) : "—"}</td>
                  <td className="p-2 text-right">{l.credit ? inr(l.credit) : "—"}</td>
                  <td className="p-2 text-right font-medium">{inr(l.balance)}</td>
                </tr>
              ))}
              {data.lines.length === 0 && (
                <tr><td colSpan={6} className="muted p-4 text-center">No postings for this account.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

type DraftLine = { account_id: string; debit: string; credit: string; description: string };
const blankLine = (): DraftLine => ({ account_id: "", debit: "", credit: "", description: "" });

function NewEntryModal({
  accounts, onClose, onPosted,
}: { accounts: any[]; onClose: () => void; onPosted: () => void }) {
  const postable = accounts.filter((a) => a.is_postable);
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10));
  const [memo, setMemo] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([blankLine(), blankLine()]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const totalDebit = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const totalCredit = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
  const balanced = totalDebit > 0 && Math.abs(totalDebit - totalCredit) < 0.005;

  function setLine(i: number, patch: Partial<DraftLine>) {
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  }

  async function submit() {
    setErr("");
    const payloadLines = lines
      .filter((l) => l.account_id && (Number(l.debit) || Number(l.credit)))
      .map((l) => ({
        account_id: Number(l.account_id),
        debit: Number(l.debit) || 0,
        credit: Number(l.credit) || 0,
        description: l.description,
      }));
    if (payloadLines.length < 2) { setErr("Add at least two lines with an account and an amount."); return; }
    setBusy(true);
    try {
      await api.post("/api/journal", { entry_date: entryDate, memo, lines: payloadLines });
      onPosted();
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
          <h3 className="text-lg font-semibold">New Journal Entry</h3>
          <button className="btn-ghost" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="muted text-xs">Date</label>
            <input type="date" className="input" value={entryDate}
              onChange={(e) => setEntryDate(e.target.value)} />
          </div>
          <div>
            <label className="muted text-xs">Memo</label>
            <input className="input" value={memo} placeholder="e.g. Accrue office rent"
              onChange={(e) => setMemo(e.target.value)} />
          </div>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="muted text-left text-xs">
              <th className="pb-1">Account</th>
              <th className="pb-1 text-right">Debit</th>
              <th className="pb-1 text-right">Credit</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={i}>
                <td className="py-1 pr-2">
                  <select className="input" value={l.account_id}
                    onChange={(e) => setLine(i, { account_id: e.target.value })}>
                    <option value="">Select account…</option>
                    {postable.map((a) => (
                      <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                    ))}
                  </select>
                </td>
                <td className="py-1 pr-2">
                  <input type="number" className="input text-right" value={l.debit}
                    onChange={(e) => setLine(i, { debit: e.target.value, credit: "" })} />
                </td>
                <td className="py-1 pr-2">
                  <input type="number" className="input text-right" value={l.credit}
                    onChange={(e) => setLine(i, { credit: e.target.value, debit: "" })} />
                </td>
                <td className="py-1">
                  {lines.length > 2 && (
                    <button className="btn-ghost" onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}>
                      <Trash2 size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-semibold">
              <td className="pt-2">
                <button className="btn-ghost" onClick={() => setLines((ls) => [...ls, blankLine()])}>
                  <Plus size={14} /> Add line
                </button>
              </td>
              <td className="pt-2 text-right">{inr(totalDebit)}</td>
              <td className="pt-2 text-right">{inr(totalCredit)}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>

        <div className="mt-3 flex items-center justify-between">
          <span className={`badge ${balanced ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
            {balanced ? "✓ Balanced" : `Difference: ${inr(totalDebit - totalCredit)}`}
          </span>
          {err && <span className="text-sm text-red-500">{err}</span>}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={!balanced || busy}>
            {busy ? "Posting…" : "Post entry"}
          </button>
        </div>
      </div>
    </div>
  );
}
