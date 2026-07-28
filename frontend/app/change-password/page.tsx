"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";
import { BrandLogo } from "@/components/Logo";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api.get("/api/auth/me").then((m) => {
      setMe(m);
      if (!m.must_change_password) router.replace("/dashboard");
    }).catch(() => router.replace("/login"));
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    if (next.length < 8) {
      setErr("New password must be at least 8 characters.");
      return;
    }
    if (next !== confirm) {
      setErr("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/api/auth/change-password", {
        current_password: current, new_password: next,
      });
      router.replace("/dashboard");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-md">
        <div className="mb-6">
          <BrandLogo size="lg" />
        </div>
        <h1 className="mb-1 text-lg font-bold">Set your password</h1>
        <p className="muted mb-5 text-sm">
          {me ? `Welcome, ${me.full_name}. ` : ""}
          You're signed in with a temporary password — set your own before continuing.
        </p>

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="muted text-xs">Temporary password</label>
            <input className="input" type="password" value={current}
              onChange={(e) => setCurrent(e.target.value)} required />
          </div>
          <div>
            <label className="muted text-xs">New password</label>
            <input className="input" type="password" value={next}
              onChange={(e) => setNext(e.target.value)} required minLength={8} />
          </div>
          <div>
            <label className="muted text-xs">Confirm new password</label>
            <input className="input" type="password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} required minLength={8} />
          </div>
          {err && <p className="text-sm text-red-500">{err}</p>}
          <button className="btn-primary w-full justify-center" disabled={loading}>
            {loading ? "Saving…" : "Set password"}
          </button>
        </form>

        <button className="btn-ghost mt-3 w-full justify-center text-xs" onClick={logout}>
          Log out
        </button>
      </div>
    </div>
  );
}
