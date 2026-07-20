"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { BrandLogo } from "@/components/Logo";

const DEMO = [
  ["cfo@demo.io", "CFO — full access"],
  ["accountant@demo.io", "Accountant"],
  ["auditor@demo.io", "Auditor — read only"],
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("cfo@demo.io");
  const [password, setPassword] = useState("demo1234");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-md">
        <div className="mb-6">
          <BrandLogo size="lg" />
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="muted text-xs">Email</label>
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="muted text-xs">Password</label>
            <input className="input" type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} />
          </div>
          {err && <p className="text-sm text-red-500">{err}</p>}
          <button className="btn-primary w-full justify-center" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-5 border-t pt-4" style={{ borderColor: "var(--border)" }}>
          <p className="muted mb-2 text-xs">Demo accounts (password: demo1234)</p>
          <div className="flex flex-wrap gap-2">
            {DEMO.map(([e, label]) => (
              <button key={e} onClick={() => setEmail(e)}
                className="badge border" style={{ borderColor: "var(--border)" }} title={label}>
                {e}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
