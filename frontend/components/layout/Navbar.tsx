"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Trophy, TrendingUp, BarChart3, Brain, User } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "首页", icon: Trophy },
  { href: "/leagues", label: "联赛中心", icon: TrendingUp },
  { href: "/predict", label: "单场预测", icon: BarChart3 },
  { href: "/backtest", label: "回测系统", icon: Brain },
  { href: "/account", label: "账户", icon: User },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 font-bold text-xl text-primary-700">
          <Trophy className="h-6 w-6" />
          <span>Football Quant</span>
        </Link>
        <nav className="hidden md:flex items-center gap-1">
          {navItems.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                pathname === href
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
