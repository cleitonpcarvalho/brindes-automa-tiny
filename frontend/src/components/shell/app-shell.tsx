"use client";

import { Sidebar } from "@/components/shell/sidebar";
import { SidebarProvider, useSidebar } from "@/components/shell/sidebar-context";
import { cn } from "cn";

function AppShellContent({ children }: { children: React.ReactNode }) {
  const { collapsed } = useSidebar();

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className={cn("transition-[padding] duration-150", collapsed ? "pl-14" : "pl-60")}>
        <main className="min-h-screen w-full">
          <div className="mx-auto max-w-[1440px] px-8 py-6">{children}</div>
        </main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <AppShellContent>{children}</AppShellContent>
    </SidebarProvider>
  );
}
