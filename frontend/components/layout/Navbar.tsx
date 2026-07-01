"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  CalendarDays,
  Gauge,
  Radio,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "控制台", icon: Gauge },
  { href: "/today", label: "今日", icon: CalendarDays },
  { href: "/predict", label: "预测", icon: Search },
  { href: "/stats", label: "统计", icon: BarChart3 },
  { href: "/system", label: "系统", icon: Activity },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        <Link href="/" className="flex min-w-0 items-center gap-2 text-slate-950">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-slate-950 text-white">
            <Radio className="h-4 w-4" />
          </span>
          <span className="truncate text-lg font-semibold">FootballQuant</span>
        </Link>
        <nav className="flex items-center gap-1 overflow-x-auto">
          {navItems.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                pathname === href || (href !== "/" && pathname.startsWith(href))
                  ? "bg-primary-50 text-primary-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
