import type { StatusVariacao } from "@/lib/api/types"

/**
 * `status` da Variacao = a situação dela em relação ao Tiny. Fonte única
 * do rótulo legível e da variante visual do badge — usada pela tabela de
 * Produtos, pelo filtro de situação e pela tela de detalhe da variação.
 * O backend também manda `status_rotulo` pronto; este mapa cobre o caso do
 * filtro (que monta as opções a partir das chaves).
 */
export const ROTULO_STATUS_VARIACAO: Record<StatusVariacao, string> = {
  pendente: "Pendente",
  aguardando: "Aguardando reposição",
  cadastrado: "Cadastrado no Tiny",
  descontinuado: "Descontinuado",
  erro: "Erro ao cadastrar",
}

export const VARIANTE_BADGE_STATUS: Record<StatusVariacao, "success" | "warning" | "error" | "neutral"> = {
  cadastrado: "success",
  aguardando: "warning",
  erro: "error",
  pendente: "neutral",
  descontinuado: "neutral",
}

export function varianteBadgeStatus(status: StatusVariacao | null | undefined) {
  return (status && VARIANTE_BADGE_STATUS[status]) ?? "neutral"
}
