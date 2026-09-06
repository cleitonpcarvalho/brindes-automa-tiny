"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowRightLeft,
  LayoutDashboard,
  LogOut,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Terminal,
} from "lucide-react";
import { cn } from "cn";
import { useSidebar } from "@/components/shell/sidebar-context";
import { useLogout, useMe } from "@/lib/api/hooks";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Visão geral", icon: LayoutDashboard },
  { href: "/instancias", label: "Instâncias", icon: Network },
  { href: "/sincronizacoes", label: "Sincronizações", icon: ArrowRightLeft },
  { href: "/logs-e-alertas", label: "Logs e Alertas", icon: Terminal },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];

function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/);
  const letras = partes.slice(0, 2).map((parte) => parte[0]?.toUpperCase() ?? "");
  return letras.join("") || "?";
}

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, setCollapsed } = useSidebar();
  const { data: me } = useMe();
  const logout = useLogout();

  const nomeExibido = me?.nome || me?.email || "…";

  return (
    <aside
      className={cn(
        "fixed top-0 left-0 z-50 flex h-full flex-col justify-between border-r border-border bg-card transition-[width] duration-150",
        collapsed ? "w-14" : "w-60",
      )}
    >
      <div className="flex flex-col">
        <div className="flex h-14 items-center justify-between border-b border-border px-4">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ArrowRightLeft size={16} />
            </div>
            {!collapsed && (
              <div className="flex min-w-0 flex-col">
                <span className="truncate text-body-medium leading-tight font-semibold text-foreground">
                  Automa Soluct
                </span>
                <span className="text-caption-label leading-tight text-muted-foreground">Sync ERP</span>
              </div>
            )}
          </div>
        </div>

        <div className="px-3 py-2">
          {!collapsed && (
            <div className="px-2 py-1 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
              Plataforma
            </div>
          )}
          <nav className="mt-1 flex flex-col gap-0.5">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "flex h-8 items-center justify-between rounded-lg px-2 text-body-default transition-colors outline-none",
                    "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card",
                    active
                      ? "bg-primary-subtle font-medium text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <Icon size={18} />
                    {!collapsed && <span>{item.label}</span>}
                  </span>
                  {!collapsed && item.badge && (
                    <span className="rounded border border-border bg-secondary px-1.5 py-px text-code-inline text-muted-foreground">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      <div className="flex flex-col border-t border-border">
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          className="flex h-9 items-center justify-center text-muted-foreground transition-colors outline-none hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:-outline-offset-2"
          aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
        <div className="flex items-center justify-between p-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="relative shrink-0">
              <div className="flex size-8 items-center justify-center rounded-full border border-border bg-secondary text-caption-medium font-semibold text-foreground">
                {iniciais(nomeExibido)}
              </div>
              <span className="absolute right-0 bottom-0 size-2.5 rounded-full bg-success ring-2 ring-card" />
            </div>
            {!collapsed && (
              <div className="flex min-w-0 flex-col">
                <span className="truncate text-body-medium leading-tight font-medium text-foreground">
                  {nomeExibido}
                </span>
                <span className="truncate text-caption-label leading-tight text-muted-foreground">
                  {me?.email}
                </span>
              </div>
            )}
          </div>
          {!collapsed && (
            <button
              type="button"
              title="Sair"
              onClick={() => logout.mutate()}
              className="flex size-7 items-center justify-center rounded text-muted-foreground transition-colors outline-none hover:bg-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
            >
              <LogOut size={16} />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
