import type { EventoLog } from "@/lib/api/types"

/** Rótulo e cor do desfecho de um SKU numa execução (tabela de auditoria). */
export const ROTULO_RESULTADO: Record<EventoLog, string> = {
  geral: "Geral",
  criado: "Cadastrado",
  vinculado: "Já cadastrado",
  bloqueado: "Ignorado / bloqueado",
  erro: "Erro",
  imagens: "Imagens sincronizadas",
  imagens_erro: "Falha nas imagens",
}

export const VARIANTE_RESULTADO: Record<
  EventoLog,
  "success" | "warning" | "error" | "neutral"
> = {
  geral: "neutral",
  criado: "success",
  vinculado: "neutral",
  bloqueado: "warning",
  erro: "error",
  imagens: "success",
  imagens_erro: "error",
}
