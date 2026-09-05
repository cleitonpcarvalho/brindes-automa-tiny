/** Formatação de números, tempo relativo e duração — usado nas telas de dashboard e instâncias. */

export function formatarNumero(valor: number): string {
  return valor.toLocaleString("pt-BR");
}

/** "agora", "há 40min", "há 2h14", "há 3d". */
export function formatarTempoRelativo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return "agora";
  if (diffMin < 60) return `há ${diffMin}min`;

  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) {
    const restoMin = diffMin % 60;
    return restoMin > 0 ? `há ${diffH}h${String(restoMin).padStart(2, "0")}` : `há ${diffH}h`;
  }

  const diffDias = Math.floor(diffH / 24);
  return `há ${diffDias}d`;
}

export function formatarDuracao(segundos: number | null | undefined): string {
  if (segundos == null) return "—";
  if (segundos < 60) return `${Math.round(segundos)}s`;
  const minutos = Math.floor(segundos / 60);
  const resto = Math.round(segundos % 60);
  return resto > 0 ? `${minutos}min ${resto}s` : `${minutos}min`;
}

export type EstadoToken = "expirado" | "urgente" | "ok" | "pendente";

export function formatarExpiracaoToken(iso: string | null | undefined): {
  texto: string;
  estado: EstadoToken;
} {
  if (!iso) return { texto: "Não configurado", estado: "pendente" };

  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return { texto: "Expirado", estado: "expirado" };

  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 60) return { texto: `Expira em ${diffMin}min`, estado: "urgente" };

  const diffH = Math.round(diffMin / 60);
  return { texto: `Expira em ${diffH}h`, estado: diffH <= 2 ? "urgente" : "ok" };
}
