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
  parcial: "Parcial",
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

/**
 * O 3º número (`total_ignorados` = variações ainda `pendente`) muda de
 * significado com o estado: enquanto a execução está viva a maioria dessas
 * variações ainda NÃO foi processada — chamá-las de "bloqueadas" seria
 * incorreto. Só depois de uma rodada COMPLETA as que restam são de fato as
 * que não puderam ser cadastradas.
 */
export function rotuloRestantes(estado: CadastroTinyEstadoEnum): string {
  return estado === "concluido" || estado === "parcial" ? "não cadastrados" : "a fazer"
}
