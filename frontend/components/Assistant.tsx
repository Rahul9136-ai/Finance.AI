"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Bot, Send, User } from "lucide-react";

type Msg = { role: "user" | "ai"; text: string; grounded?: string[] };

const SUGGESTIONS = [
  "What is my cash balance?",
  "Show pending GST",
  "What is my profit?",
  "How much do customers owe me?",
];

export default function Assistant({ compact = false }: { compact?: boolean }) {
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "ai", text: "Hi! Ask me about cash, receivables, payables, GST, revenue or profit — I answer from your live ledger." },
  ]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState<string>("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get("/api/ai/status").then((r) => setProvider(r.provider)).catch(() => {});
  }, []);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [msgs]);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api.post("/api/ai/chat", { question });
      setMsgs((m) => [...m, { role: "ai", text: r.answer, grounded: r.grounded_on }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "ai", text: "Error: " + e.message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center gap-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
          <Bot size={16} />
        </div>
        <div>
          <p className="text-sm font-semibold">Finance Assistant</p>
          <p className="muted text-xs">
            engine: <span className="font-mono">{provider || "…"}</span>
          </p>
        </div>
      </div>

      <div className={`flex-1 space-y-3 overflow-y-auto pr-1 ${compact ? "max-h-64" : "min-h-[280px]"}`}>
        {msgs.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === "user" ? "justify-end" : ""}`}>
            {m.role === "ai" && <Bot size={16} className="mt-1 shrink-0 text-brand-500" />}
            <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
              m.role === "user" ? "bg-brand-600 text-white" : "border"
            }`} style={m.role === "ai" ? { borderColor: "var(--border)" } : {}}>
              {m.text}
              {m.grounded && m.grounded.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {m.grounded.map((g, gi) => (
                    <span key={`${g}-${gi}`} className="badge bg-emerald-100 text-emerald-700">🔧 {g}</span>
                  ))}
                </div>
              )}
            </div>
            {m.role === "user" && <User size={16} className="mt-1 shrink-0" />}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => ask(s)}
            className="badge border" style={{ borderColor: "var(--border)" }}>{s}</button>
        ))}
      </div>

      <form onSubmit={(e) => { e.preventDefault(); ask(q); }} className="mt-2 flex gap-2">
        <input className="input" placeholder="Ask a finance question…" value={q}
          onChange={(e) => setQ(e.target.value)} />
        <button className="btn-primary" disabled={busy}><Send size={16} /></button>
      </form>
    </div>
  );
}
