"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import Assistant from "@/components/Assistant";
import { api, inr } from "@/lib/api";
import { downloadCsv, toCsv } from "@/lib/csv";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  AreaChart, Area, Legend,
} from "recharts";
import {
  Wallet, TrendingUp, TrendingDown, Receipt, ArrowDownRight, ArrowUpRight, Download,
} from "lucide-react";

type KPI = {
  cash_balance: number; receivables: number; payables: number;
  revenue: number; expenses: number; profit: number; gst_due: number;
};

function Kpi({ label, value, icon: Icon, tone }: any) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <span className="muted text-sm">{label}</span>
        <div className={`grid h-9 w-9 place-items-center rounded-lg ${tone}`}>
          <Icon size={18} />
        </div>
      </div>
      <p className="mt-2 text-2xl font-bold">{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const [kpi, setKpi] = useState<KPI | null>(null);
  const [rev, setRev] = useState<any[]>([]);
  const [aging, setAging] = useState<any[]>([]);
  const [forecast, setForecast] = useState<any[]>([]);

  useEffect(() => {
    api.get("/api/dashboard/kpis").then(setKpi).catch(() => {});
    api.get("/api/dashboard/revenue-series?months=6").then(setRev).catch(() => {});
    api.get("/api/dashboard/aging?kind=AR").then((a) =>
      setAging(Object.entries(a).map(([bucket, amount]) => ({ bucket, amount })))
    ).catch(() => {});
    api.get("/api/ai/forecast?horizon_days=90").then((f) => setForecast(f.series)).catch(() => {});
  }, []);

  function exportCsv() {
    if (!kpi) return;
    const summary = toCsv(
      Object.entries(kpi).map(([metric, value]) => ({ metric, value })),
      ["metric", "value"],
    );
    const revenueTable = rev.length ? "\n\nRevenue vs Expense\n" + toCsv(rev) : "";
    const agingTable = aging.length ? "\n\nAR Aging\n" + toCsv(aging) : "";
    downloadCsv(`dashboard-${new Date().toISOString().slice(0, 10)}.csv`,
      summary + revenueTable + agingTable);
  }

  return (
    <Shell>
      <div className="mb-1 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button className="btn-ghost" onClick={exportCsv} disabled={!kpi}>
          <Download size={16} /> Export CSV
        </button>
      </div>
      <p className="muted mb-5 text-sm">Real-time financial health, powered by your live ledger.</p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Cash & Bank" value={kpi ? inr(kpi.cash_balance) : "…"}
          icon={Wallet} tone="bg-emerald-100 text-emerald-700" />
        <Kpi label="Receivables" value={kpi ? inr(kpi.receivables) : "…"}
          icon={ArrowDownRight} tone="bg-sky-100 text-sky-700" />
        <Kpi label="Payables" value={kpi ? inr(kpi.payables) : "…"}
          icon={ArrowUpRight} tone="bg-amber-100 text-amber-700" />
        <Kpi label="GST Due" value={kpi ? inr(kpi.gst_due) : "…"}
          icon={Receipt} tone="bg-rose-100 text-rose-700" />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Kpi label="Revenue" value={kpi ? inr(kpi.revenue) : "…"}
          icon={TrendingUp} tone="bg-indigo-100 text-indigo-700" />
        <Kpi label="Expenses" value={kpi ? inr(kpi.expenses) : "…"}
          icon={TrendingDown} tone="bg-orange-100 text-orange-700" />
        <Kpi label="Profit / Loss"
          value={kpi ? inr(kpi.profit) : "…"}
          icon={kpi && kpi.profit >= 0 ? TrendingUp : TrendingDown}
          tone={kpi && kpi.profit >= 0 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h3 className="mb-3 font-semibold">Revenue vs Expense (6 months)</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={rev}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
              <XAxis dataKey="month" fontSize={12} />
              <YAxis fontSize={12} tickFormatter={(v) => `${v / 1000}k`} />
              <Tooltip formatter={(v: number) => inr(v)} />
              <Legend />
              <Bar dataKey="revenue" fill="#6366f1" radius={[4, 4, 0, 0]} />
              <Bar dataKey="expense" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="mb-3 font-semibold">AR Aging</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={aging} layout="vertical">
              <XAxis type="number" hide />
              <YAxis dataKey="bucket" type="category" fontSize={12} width={60} />
              <Tooltip formatter={(v: number) => inr(v)} />
              <Bar dataKey="amount" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h3 className="mb-1 font-semibold">90-Day Cashflow Forecast</h3>
          <p className="muted mb-3 text-xs">AI projection from AR/AP due dates + current cash.</p>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={forecast}>
              <defs>
                <linearGradient id="cf" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
              <XAxis dataKey="date" fontSize={11} tickFormatter={(d) => d.slice(5)} />
              <YAxis fontSize={12} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip formatter={(v: number) => inr(v)} />
              <Area type="monotone" dataKey="projected_cash" stroke="#6366f1"
                fill="url(#cf)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <Assistant compact />
        </div>
      </div>
    </Shell>
  );
}
