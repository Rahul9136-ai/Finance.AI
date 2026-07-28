"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";
import { BrandLogo } from "@/components/Logo";
import {
  LayoutDashboard, BookOpen, FileText, Bot, Moon, Sun, LogOut, Users,
} from "lucide-react";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/journal", label: "General Ledger", icon: BookOpen },
  { href: "/invoices", label: "Invoices (AR/AP)", icon: FileText },
  { href: "/assistant", label: "AI Assistant", icon: Bot },
];

function hasPerm(perms: string[] | undefined, needed: string): boolean {
  if (!perms) return false;
  if (perms.includes("*:*") || perms.includes(needed)) return true;
  const [resource, action] = needed.split(":");
  return perms.includes(`${resource}:*`) || perms.includes(`*:${action}`);
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<any>(null);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setDark(document.documentElement.classList.contains("dark"));
    api.get("/api/auth/me").then((m) => {
      setMe(m);
      if (m.must_change_password && pathname !== "/change-password") {
        router.replace("/change-password");
      }
    }).catch(() => {});
  }, [router, pathname]);

  function toggleTheme() {
    const el = document.documentElement;
    const next = !el.classList.contains("dark");
    el.classList.toggle("dark", next);
    localStorage.theme = next ? "dark" : "light";
    setDark(next);
  }

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-64 shrink-0 border-r p-4 md:block"
        style={{ borderColor: "var(--border)", background: "var(--card)" }}>
        <div className="mb-6 px-1">
          <BrandLogo size="sm" />
        </div>
        <nav className="space-y-1">
          {NAV.map((n) => {
            const active = pathname === n.href;
            const Icon = n.icon;
            return (
              <Link key={n.href} href={n.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium ${
                  active ? "bg-brand-600 text-white" : "hover:bg-black/5 dark:hover:bg-white/5"
                }`}>
                <Icon size={18} />
                {n.label}
              </Link>
            );
          })}
          {hasPerm(me?.permissions, "user:create") && (
            <Link href="/users"
              className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium ${
                pathname === "/users" ? "bg-brand-600 text-white" : "hover:bg-black/5 dark:hover:bg-white/5"
              }`}>
              <Users size={18} />
              Users
            </Link>
          )}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b px-6 py-3"
          style={{ borderColor: "var(--border)", background: "var(--card)" }}>
          <div className="text-sm">
            {me && (
              <span>
                <span className="font-semibold">{me.full_name}</span>{" "}
                <span className="badge bg-brand-100 text-brand-700">{me.role}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-ghost" onClick={toggleTheme} aria-label="Toggle theme">
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button className="btn-ghost" onClick={logout}>
              <LogOut size={16} /> Logout
            </button>
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
