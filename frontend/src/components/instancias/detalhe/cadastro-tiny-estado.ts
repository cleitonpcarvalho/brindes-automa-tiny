import type { CadastroTinyEstadoEnum } from "@/lib/api/types"

/**
 * Rótulo + variante de badge de cada estado da sincronização em massa com o
 * Tiny (pause/resume). Fonte única — usada pelo bloco "Cadastro no Tiny" e
 * pelos testes.
 */
export const ROTULO_ESTADO_CADASTRO_TINY: Record<CadastroTinyEstadoEnum, string> = {
  pronto: "Pronto",
  sincronizando: "Sincronizando",
  pausando: "Pausando…",
  pausado: "Pausado",
  interrompido: "Interrompido",
  concluido: "Concluído",
  parcial: "Parcial / com erros",
}

export const VARIANTE_ESTADO_CADASTRO_TINY: Record<
  CadastroTinyEstadoEnum,
  "success" | "warning" | "error" | "neutral"
> = {
  pronto: "neutral",
  sincronizando: "warning",
  pausando: "neutral",
  pausado: "warning",
  interrompido: "error",
  concluido: "success",
  parcial: "warning",
}
