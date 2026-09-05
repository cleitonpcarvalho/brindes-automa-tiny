"use client";

import { useEffect, useState } from "react";

/**
 * Como localStorage, é por navegador/aba — cada operador guarda a própria
 * preferência (ex.: sidebar colapsada), sem precisar de uma coluna no
 * backend pra isso.
 */
export function usePersistedState(key: string, defaultValue: boolean) {
  const [value, setValue] = useState(defaultValue);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (stored !== null) setValue(stored === "true");
    } catch {
      // localStorage indisponível (modo privado, etc.) — segue com o padrão
    }
    setHydrated(true);
  }, [key]);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(key, String(value));
    } catch {
      // ignora — preferência só não persiste
    }
  }, [key, value, hydrated]);

  return [value, setValue] as const;
}
