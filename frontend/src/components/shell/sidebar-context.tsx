"use client";

import { createContext, useContext } from "react";
import { usePersistedState } from "@/lib/hooks/use-persisted-state";

interface SidebarContextValue {
  collapsed: boolean;
  setCollapsed: (value: boolean | ((current: boolean) => boolean)) => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = usePersistedState("sidebar-collapsed", false);
  return <SidebarContext.Provider value={{ collapsed, setCollapsed }}>{children}</SidebarContext.Provider>;
}

export function useSidebar() {
  const context = useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar precisa estar dentro de um <SidebarProvider>.");
  }
  return context;
}
