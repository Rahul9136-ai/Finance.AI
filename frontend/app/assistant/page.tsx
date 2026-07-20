"use client";
import { useState } from "react";
import Shell from "@/components/Shell";
import Assistant from "@/components/Assistant";
import { api } from "@/lib/api";
import { ShieldAlert, ScanLine } from "lucide-react";

export default function AssistantPage() {
  const [text, setText] = useState(
    "TAX INVOICE\nInvoice No: INV-7788\nDate: 12/07/2026\nGSTIN: 27BBBBB1111B1Z5\nSteel rods 100 units\nTotal: 1,18,000.00"
  );
  const [read, setRead] = useState<any>(null);
  const [amount, setAmount] = useState("50000");
  const [fraud, setFraud] = useState<any>(null);

  return (
    <Shell>
      <h1 className="mb-1 text-2xl font-bold">AI Assistant</h1>
      <p className="muted mb-5 text-sm">
        Chat grounded in live data, invoice OCR extraction, and fraud scoring — all runnable with
        no external key.
      </p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <Assistant />
        </div>

        <div className="space-y-4">
          <div className="card">
            <h3 className="mb-2 flex items-center gap-2 font-semibold">
              <ScanLine size={18} className="text-brand-500" /> AI Invoice Reader
            </h3>
            <textarea className="input h-28 font-mono text-xs" value={text}
              onChange={(e) => setText(e.target.value)} />
            <button className="btn-primary mt-2"
              onClick={() => api.post("/api/ai/read-invoice", { text }).then(setRead)}>
              Extract fields
            </button>
            {read && (
              <pre className="mt-3 overflow-x-auto rounded-xl border p-3 text-xs"
                style={{ borderColor: "var(--border)" }}>
                {JSON.stringify(read, null, 2)}
              </pre>
            )}
          </div>

          <div className="card">
            <h3 className="mb-2 flex items-center gap-2 font-semibold">
              <ShieldAlert size={18} className="text-rose-500" /> AI Fraud Detection
            </h3>
            <div className="flex gap-2">
              <input className="input" value={amount} onChange={(e) => setAmount(e.target.value)}
                placeholder="Amount" />
              <button className="btn-primary"
                onClick={() =>
                  api.post("/api/ai/fraud-check", { amount: Number(amount), vendor_id: 1 }).then(setFraud)
                }>
                Check
              </button>
            </div>
            {fraud && (
              <div className="mt-3">
                <span className={`badge ${
                  fraud.risk_level === "high" ? "bg-rose-100 text-rose-700"
                  : fraud.risk_level === "medium" ? "bg-amber-100 text-amber-700"
                  : "bg-emerald-100 text-emerald-700"}`}>
                  {fraud.risk_level} risk · score {fraud.risk_score}
                </span>
                <ul className="mt-2 list-inside list-disc text-sm">
                  {fraud.reasons.map((r: string) => <li key={r}>{r}</li>)}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </Shell>
  );
}
