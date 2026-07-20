"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, getToken, inr } from "@/lib/api";
import { Plus, Upload, Pencil, FileSpreadsheet, FileText, ScanLine, FileType, X } from "lucide-react";

type Invoice = {
  id: number; kind: string; number: string; issue_date: string; due_date: string;
  subtotal: number; tax_total: number; total: number; amount_paid: number;
  status: string; entry_mode: string; tds_total: number;
};

const modeIcon: Record<string, any> = {
  pdf: FileText, excel: FileSpreadsheet, csv: FileSpreadsheet,
  image: ScanLine, word: FileType, manual: Pencil,
};

// Every format the ingestion pipeline can read.
const ACCEPT_ALL = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.gif,.xlsx,.xlsm,.xls,.csv,.tsv,.docx,.txt,.htm,.html";

const statusTone: Record<string, string> = {
  paid: "bg-emerald-100 text-emerald-700",
  open: "bg-sky-100 text-sky-700",
  partial: "bg-amber-100 text-amber-700",
  draft: "bg-slate-200 text-slate-600",
  void: "bg-rose-100 text-rose-700",
};

export default function InvoicesPage() {
  const [kind, setKind] = useState<"AR" | "AP">("AR");
  const [rows, setRows] = useState<Invoice[]>([]);
  const [vendors, setVendors] = useState<any[]>([]);
  const [showBill, setShowBill] = useState(false);
  const [flash, setFlash] = useState("");

  function load() {
    api.get(`/api/invoices?kind=${kind}`).then(setRows).catch(() => {});
  }
  function loadVendors() {
    api.get("/api/vendors").then(setVendors).catch(() => {});
  }
  useEffect(() => { loadVendors(); }, []);
  // Block-body effect so it returns undefined — never hand React a Promise as a
  // cleanup fn (that throws "destroy is not a function" on unmount).
  useEffect(() => { load(); }, [kind]);

  async function pay(inv: Invoice) {
    const outstanding = inv.total - inv.amount_paid;
    try {
      await api.post(`/api/invoices/${inv.id}/pay`, {
        amount: outstanding,
        pay_date: new Date().toISOString().slice(0, 10),
        method: "bank",
        reference: "UI-PAY",
      });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  return (
    <Shell>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Invoices</h1>
          <p className="muted text-sm">
            {kind === "AR" ? "Accounts Receivable — customer invoices" : "Accounts Payable — vendor bills"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 rounded-xl border p-1" style={{ borderColor: "var(--border)" }}>
            {(["AR", "AP"] as const).map((k) => (
              <button key={k} onClick={() => setKind(k)}
                className={`btn ${kind === k ? "bg-brand-600 text-white" : ""}`}>{k}</button>
            ))}
          </div>
          {kind === "AP" && (
            <button className="btn-primary" onClick={() => setShowBill(true)}>
              <Plus size={16} /> New Bill
            </button>
          )}
        </div>
      </div>

      {flash && (
        <div className="mb-4 rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm text-emerald-800">
          {flash}
          <button className="ml-3 underline" onClick={() => setFlash("")}>dismiss</button>
        </div>
      )}

      {showBill && (
        <NewBillModal
          vendors={vendors}
          onClose={() => setShowBill(false)}
          onPosted={(res: any) => {
            setShowBill(false);
            load();
            loadVendors();
            if (res?.vendor_created && res.vendor) {
              setFlash(`New vendor captured & account created: ${res.vendor.name}`);
            }
          }}
        />
      )}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="muted border-b text-left text-xs" style={{ borderColor: "var(--border)" }}>
              <th className="p-2">Number</th>
              {kind === "AP" && <th className="p-2">Mode</th>}
              <th className="p-2">Issued</th>
              <th className="p-2">Due</th>
              <th className="p-2 text-right">Subtotal</th>
              <th className="p-2 text-right">Tax</th>
              {kind === "AP" && <th className="p-2 text-right">TDS</th>}
              <th className="p-2 text-right">Total</th>
              <th className="p-2 text-right">Paid</th>
              <th className="p-2">Status</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b" style={{ borderColor: "var(--border)" }}>
                <td className="p-2 font-medium">{r.number}</td>
                {kind === "AP" && (
                  <td className="p-2">
                    <span className="badge border inline-flex items-center gap-1" style={{ borderColor: "var(--border)" }}>
                      {(() => { const I = modeIcon[r.entry_mode] || Pencil; return <I size={12} />; })()}
                      {r.entry_mode}
                    </span>
                  </td>
                )}
                <td className="p-2">{r.issue_date}</td>
                <td className="p-2">{r.due_date}</td>
                <td className="p-2 text-right">{inr(r.subtotal)}</td>
                <td className="p-2 text-right">{inr(r.tax_total)}</td>
                {kind === "AP" && <td className="p-2 text-right">{r.tds_total ? inr(r.tds_total) : "—"}</td>}
                <td className="p-2 text-right font-semibold">{inr(r.total)}</td>
                <td className="p-2 text-right">{inr(r.amount_paid)}</td>
                <td className="p-2"><span className={`badge ${statusTone[r.status]}`}>{r.status}</span></td>
                <td className="p-2 text-right">
                  {(r.status === "open" || r.status === "partial") && (
                    <button className="btn-ghost" onClick={() => pay(r)}>
                      {kind === "AR" ? "Receive" : "Pay"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={11} className="muted p-4 text-center">No invoices.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

type Mode = "manual" | "pdf" | "excel" | "image";
const today = () => new Date().toISOString().slice(0, 10);
const plusDays = (n: number) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);

function NewBillModal({
  vendors, onClose, onPosted,
}: { vendors: any[]; onClose: () => void; onPosted: (res: any) => void }) {
  const [mode, setMode] = useState<Mode>("manual");
  const [detectedMode, setDetectedMode] = useState<string | null>(null);
  const [number, setNumber] = useState("");
  const [vendorId, setVendorId] = useState("");        // "" | id | "__new__"
  const [newVendorName, setNewVendorName] = useState("");
  const [newVendorGstin, setNewVendorGstin] = useState("");
  const [issueDate, setIssueDate] = useState(today());
  const [dueDate, setDueDate] = useState(plusDays(30));
  const [description, setDescription] = useState("");
  const [base, setBase] = useState("");
  const [gst, setGst] = useState("");
  const [tds, setTds] = useState("");
  const [dist, setDist] = useState<any>(null);
  const [extracted, setExtracted] = useState<any>(null);
  const [parsing, setParsing] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [itemized, setItemized] = useState(false);
  const [items, setItems] = useState<{ description: string; amount: string }[]>([
    { description: "", amount: "" },
  ]);
  const [cls, setCls] = useState<any>(null);  // item classification result

  // Live section distribution preview (single-total mode).
  useEffect(() => {
    if (itemized) { setDist(null); return; }
    const b = Number(base);
    if (!b) { setDist(null); return; }
    const t = setTimeout(() => {
      api.post("/api/bills/distribute", {
        base: b, gst_amount: Number(gst) || 0, tds_amount: Number(tds) || 0,
        description,
      }).then(setDist).catch(() => setDist(null));
    }, 250);
    return () => clearTimeout(t);
  }, [base, gst, tds, description, itemized]);

  // Live tax classification per item (itemized mode).
  useEffect(() => {
    if (!itemized) { setCls(null); return; }
    const valid = items.filter((i) => i.description.trim() && Number(i.amount));
    if (!valid.length) { setCls(null); return; }
    const t = setTimeout(() => {
      api.post("/api/bills/classify", {
        items: valid.map((i) => ({ description: i.description, amount: Number(i.amount) })),
        tds_amount: Number(tds) || 0,
      }).then(setCls).catch(() => setCls(null));
    }, 300);
    return () => clearTimeout(t);
  }, [itemized, items, tds]);

  function setItem(i: number, patch: Partial<{ description: string; amount: string }>) {
    setItems((xs) => xs.map((x, idx) => (idx === i ? { ...x, ...patch } : x)));
  }

  const [aiProvider, setAiProvider] = useState<string>("");
  useEffect(() => {
    api.get("/api/ai/status").then((r) => setAiProvider(r.provider)).catch(() => {});
  }, []);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setParsing(true);
    setErr("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/bills/ingest", {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: fd,
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Parse failed");
      const data = await res.json();
      const p = data.parsed;
      setExtracted(p);
      setDetectedMode(p.entry_mode);
      if (p.invoice_number) setNumber(p.invoice_number);
      if (p.base) setBase(String(p.base));
      else if (data.distribution) setBase(String(data.distribution.base));
      if (p.gst) setGst(String(p.gst));
      if (p.tds) setTds(String(p.tds));
      if (!description) setDescription(p.invoice_number || file.name.replace(/\.[^.]+$/, ""));
      // Vendor: match an existing one (by GSTIN or name) else prep a new one.
      if (p.vendor_name || p.vendor_gstin) {
        const match = vendors.find((v) =>
          (p.vendor_gstin && v.gstin && v.gstin.toLowerCase() === p.vendor_gstin.toLowerCase()) ||
          (p.vendor_name && v.name.toLowerCase() === p.vendor_name.toLowerCase())
        );
        if (match) {
          setVendorId(String(match.id));
        } else {
          setVendorId("__new__");
          setNewVendorName(p.vendor_name || "");
          setNewVendorGstin(p.vendor_gstin || "");
        }
      }
    } catch (e: any) {
      setExtracted(null);
      setErr(e.message);
    } finally {
      setParsing(false);
    }
  }

  async function submit() {
    setErr("");
    if (!number.trim()) { setErr("Bill number is required."); return; }
    if (vendorId === "__new__" && !newVendorName.trim()) {
      setErr("Enter a name for the new vendor."); return;
    }
    const validItems = items.filter((i) => i.description.trim() && Number(i.amount));
    if (itemized && !validItems.length) { setErr("Add at least one item with an amount."); return; }
    if (!itemized && !Number(base)) { setErr("Base amount must be positive."); return; }

    const vendorPart: any = {};
    if (vendorId === "__new__") {
      vendorPart.vendor_name = newVendorName.trim();
      vendorPart.vendor_gstin = newVendorGstin.trim() || null;
    } else if (vendorId) {
      vendorPart.vendor_id = Number(vendorId);
    }
    const common = {
      number, issue_date: issueDate, due_date: dueDate,
      entry_mode: detectedMode || (mode === "manual" ? "manual" : mode),
      ...vendorPart,
    };

    setBusy(true);
    try {
      const res = itemized
        ? await api.post("/api/bills/items", {
            ...common, tds_amount: Number(tds) || 0,
            items: validItems.map((i) => ({ description: i.description, amount: Number(i.amount) })),
          })
        : await api.post("/api/bills", {
            ...common, description,
            base: Number(base), gst_amount: Number(gst) || 0, tds_amount: Number(tds) || 0,
          });
      onPosted(res);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const modes: { id: Mode; label: string; icon: any }[] = [
    { id: "manual", label: "Manual", icon: Pencil },
    { id: "pdf", label: "PDF", icon: FileText },
    { id: "excel", label: "Excel / CSV", icon: FileSpreadsheet },
    { id: "image", label: "Image / Scan", icon: ScanLine },
  ];
  const uploadHint: Record<string, string> = {
    pdf: "PDF (text or scanned — OCR runs automatically)",
    excel: "Excel or CSV (.xlsx, .xls, .csv)",
    image: "a photo or scan (.jpg, .png, .tiff…) — read with OCR",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4" onClick={onClose}>
      <div className="card mt-8 w-full max-w-3xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">New Vendor Bill</h3>
          <button className="btn-ghost" onClick={onClose}><X size={16} /></button>
        </div>

        {/* Mode of entry */}
        <label className="muted text-xs">Mode of entry</label>
        <div className="mb-4 mt-1 flex gap-1 rounded-xl border p-1" style={{ borderColor: "var(--border)", width: "fit-content" }}>
          {modes.map((m) => {
            const I = m.icon;
            return (
              <button key={m.id} onClick={() => setMode(m.id)}
                className={`btn ${mode === m.id ? "bg-brand-600 text-white" : ""}`}>
                <I size={14} /> {m.label}
              </button>
            );
          })}
        </div>

        {mode !== "manual" && (
          <div className="mb-4 rounded-xl border border-dashed p-4 text-center" style={{ borderColor: "var(--border)" }}>
            <Upload size={20} className="mx-auto mb-2 text-brand-500" />
            <p className="muted mb-2 text-sm">
              Upload {uploadHint[mode] ?? "a bill"} — the AI extracts the amounts and distributes them.
            </p>
            {/* Accept every readable format regardless of chip; the backend detects the type. */}
            <input type="file" accept={ACCEPT_ALL} onChange={onFile} className="text-sm" />
            <p className="muted mt-2 text-[11px]">Any file works: PDF · image/scan · Excel · CSV · Word</p>
            {aiProvider && aiProvider !== "rules" ? (
              <p className="mt-1 text-[11px] text-violet-600">✓ AI extraction active ({aiProvider}) — best accuracy</p>
            ) : (
              <p className="muted mt-1 text-[11px]">Rule-based reading. Add an AI key (OPENAI_API_KEY / ANTHROPIC_API_KEY) for best accuracy.</p>
            )}
            {parsing && <p className="muted mt-1 text-xs">Reading the bill…</p>}
          </div>
        )}

        {extracted && (
          <div className="mb-4 rounded-xl border p-3 text-sm" style={{ borderColor: "var(--border)" }}>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="font-semibold">Read from {extracted.entry_mode.toUpperCase()}</span>
              <span className={`badge ${extracted.engine === "ai"
                ? "bg-violet-100 text-violet-700" : "bg-slate-200 text-slate-600"}`}>
                {extracted.engine === "ai" ? "AI extraction" : "rule-based"}
              </span>
              {extracted.ocr_used && (
                <span className="badge inline-flex items-center gap-1 bg-brand-100 text-brand-700">
                  <ScanLine size={11} /> OCR
                </span>
              )}
              <span className={`badge ${
                extracted.confidence >= 0.85 ? "bg-emerald-100 text-emerald-700"
                : extracted.confidence >= 0.5 ? "bg-amber-100 text-amber-700"
                : "bg-rose-100 text-rose-700"}`}>
                {Math.round(extracted.confidence * 100)}% confidence
              </span>
              {extracted.invoice_number && <span className="muted text-xs">#{extracted.invoice_number}</span>}
            </div>
            {extracted.vendor_name && (
              <div className="mb-1 text-xs">
                Vendor: <b>{extracted.vendor_name}</b>
                {extracted.vendor_gstin && <span className="muted"> · {extracted.vendor_gstin}</span>}
                {vendorId === "__new__" && (
                  <span className="badge ml-2 bg-emerald-100 text-emerald-700">new — will be created</span>
                )}
              </div>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
              <span>Base <b>{inr(extracted.base)}</b></span>
              {extracted.cgst > 0 && <span>CGST <b>{inr(extracted.cgst)}</b></span>}
              {extracted.sgst > 0 && <span>SGST <b>{inr(extracted.sgst)}</b></span>}
              {extracted.igst > 0 && <span>IGST <b>{inr(extracted.igst)}</b></span>}
              <span>GST <b>{inr(extracted.gst)}</b></span>
              <span>TDS <b>{inr(extracted.tds)}</b></span>
              <span>Total <b>{inr(extracted.gross)}</b></span>
            </div>
            {extracted.warnings?.length > 0 && (
              <ul className="mt-2 list-inside list-disc text-xs text-amber-600">
                {extracted.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
              </ul>
            )}
            {extracted.line_items?.length > 0 && (
              <button className="btn-ghost mt-2 text-xs"
                onClick={() => {
                  setItems(extracted.line_items.map((l: any) => ({
                    description: l.description, amount: String(l.amount),
                  })));
                  setItemized(true);
                }}>
                <Plus size={12} /> Load {extracted.line_items.length} detected item(s) into itemized entry
              </button>
            )}
            <p className="muted mt-2 text-xs">Review and correct the amounts below before posting.</p>
            {extracted.text_preview && (
              <details className="mt-2 text-xs">
                <summary className="muted cursor-pointer">Show exactly what was read</summary>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border p-2"
                  style={{ borderColor: "var(--border)" }}>{extracted.text_preview}</pre>
              </details>
            )}
          </div>
        )}

        {/* Bill header */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div>
            <label className="muted text-xs">Bill number</label>
            <input className="input" value={number} onChange={(e) => setNumber(e.target.value)} placeholder="BILL-0001" />
          </div>
          <div>
            <label className="muted text-xs">Vendor</label>
            <select className="input" value={vendorId} onChange={(e) => setVendorId(e.target.value)}>
              <option value="">— none —</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              <option value="__new__">+ Capture new vendor…</option>
            </select>
          </div>
          <div>
            <label className="muted text-xs">Description</label>
            <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. office rent" />
          </div>
          <div>
            <label className="muted text-xs">Issue date</label>
            <input type="date" className="input" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
          </div>
          <div>
            <label className="muted text-xs">Due date</label>
            <input type="date" className="input" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </div>
        </div>

        {vendorId === "__new__" && (
          <div className="mt-3 grid grid-cols-1 gap-3 rounded-xl border border-emerald-300 bg-emerald-50/40 p-3 sm:grid-cols-2">
            <div className="sm:col-span-2 text-xs font-medium text-emerald-700">
              New vendor — an account will be created on save
            </div>
            <div>
              <label className="muted text-xs">Vendor name</label>
              <input className="input" value={newVendorName}
                onChange={(e) => setNewVendorName(e.target.value)} placeholder="Vendor legal name" />
            </div>
            <div>
              <label className="muted text-xs">GSTIN (optional)</label>
              <input className="input" value={newVendorGstin}
                onChange={(e) => setNewVendorGstin(e.target.value)} placeholder="27ABCDE1234F1Z5" />
            </div>
          </div>
        )}

        {/* Entry style toggle */}
        <div className="mt-4 flex items-center gap-2">
          <span className="muted text-xs">Entry:</span>
          <div className="flex gap-1 rounded-xl border p-1" style={{ borderColor: "var(--border)" }}>
            <button className={`btn ${!itemized ? "bg-brand-600 text-white" : ""}`} onClick={() => setItemized(false)}>Single total</button>
            <button className={`btn ${itemized ? "bg-brand-600 text-white" : ""}`} onClick={() => setItemized(true)}>Itemized (tax by item)</button>
          </div>
        </div>

        {!itemized ? (
          <div className="mt-3 grid grid-cols-3 gap-3">
            <div>
              <label className="muted text-xs">Base (taxable)</label>
              <input type="number" className="input text-right" value={base} onChange={(e) => setBase(e.target.value)} />
            </div>
            <div>
              <label className="muted text-xs">GST amount</label>
              <input type="number" className="input text-right" value={gst} onChange={(e) => setGst(e.target.value)} />
            </div>
            <div>
              <label className="muted text-xs">TDS withheld</label>
              <input type="number" className="input text-right" value={tds} onChange={(e) => setTds(e.target.value)} />
            </div>
          </div>
        ) : (
          <div className="mt-3">
            <table className="w-full text-sm">
              <thead>
                <tr className="muted text-left text-xs">
                  <th className="pb-1">Item description</th>
                  <th className="pb-1 text-right">Amount</th>
                  <th className="pb-1">Category (auto)</th>
                  <th className="pb-1 text-right">GST%</th>
                  <th className="pb-1 text-right">GST</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => {
                  const line = it.description.trim() && Number(it.amount)
                    ? cls?.lines?.find((l: any) => l.description === it.description.trim())
                    : null;
                  return (
                    <tr key={i}>
                      <td className="py-1 pr-2">
                        <input className="input" placeholder="e.g. Reynolds pen, Physics textbook"
                          value={it.description} onChange={(e) => setItem(i, { description: e.target.value })} />
                      </td>
                      <td className="py-1 pr-2 w-28">
                        <input type="number" className="input text-right" value={it.amount}
                          onChange={(e) => setItem(i, { amount: e.target.value })} />
                      </td>
                      <td className="py-1 pr-2 text-xs">
                        {line ? (
                          <span className="badge bg-brand-100 text-brand-700">{line.category}</span>
                        ) : <span className="muted">—</span>}
                        {line && <span className="muted ml-1">HSN {line.hsn}</span>}
                      </td>
                      <td className="py-1 pr-2 text-right">{line ? `${line.gst_rate}%` : "—"}</td>
                      <td className="py-1 pr-2 text-right">{line ? inr(line.gst_amount) : "—"}</td>
                      <td className="py-1">
                        {items.length > 1 && (
                          <button className="btn-ghost" onClick={() => setItems((xs) => xs.filter((_, j) => j !== i))}>
                            <X size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="mt-2 flex items-center justify-between">
              <button className="btn-ghost" onClick={() => setItems((xs) => [...xs, { description: "", amount: "" }])}>
                <Plus size={14} /> Add item
              </button>
              <div className="flex items-center gap-2">
                <label className="muted text-xs">TDS withheld</label>
                <input type="number" className="input text-right w-28" value={tds} onChange={(e) => setTds(e.target.value)} />
              </div>
            </div>
          </div>
        )}

        {/* Distribution preview */}
        {(() => {
          const preview = itemized ? cls : dist;
          return (
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between">
                <h4 className="font-semibold">Distribution across sections</h4>
                {preview && <span className="badge bg-emerald-100 text-emerald-700">✓ Balanced</span>}
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="muted text-left text-xs">
                    <th className="pb-1">Section</th>
                    <th className="pb-1">Account</th>
                    <th className="pb-1 text-right">Debit</th>
                    <th className="pb-1 text-right">Credit</th>
                  </tr>
                </thead>
                <tbody>
                  {preview ? preview.sections.map((s: any, i: number) => (
                    <tr key={i} className="border-t" style={{ borderColor: "var(--border)" }}>
                      <td className="py-1">{s.section}</td>
                      <td className="py-1 font-mono text-xs">{s.account_code}</td>
                      <td className="py-1 text-right">{s.side === "debit" ? inr(s.amount) : "—"}</td>
                      <td className="py-1 text-right">{s.side === "credit" ? inr(s.amount) : "—"}</td>
                    </tr>
                  )) : (
                    <tr><td colSpan={4} className="muted py-3 text-center">
                      {itemized ? "Add items to see the tax split." : "Enter a base amount to see the split."}
                    </td></tr>
                  )}
                </tbody>
                {preview && (
                  <tfoot>
                    <tr className="font-semibold">
                      <td className="pt-2" colSpan={2}>Net payable to vendor</td>
                      <td colSpan={2} className="pt-2 text-right">{inr(preview.net_payable)}</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          );
        })()}

        {err && <p className="mt-3 text-sm text-red-500">{err}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={busy || (itemized ? !cls : !dist)}>
            {busy ? "Posting…" : "Post bill"}
          </button>
        </div>
      </div>
    </div>
  );
}
