import { Badge } from "@/components/ui/badge"
import type { StatusInstancia } from "@/lib/api/types"

export const BADGE_POR_STATUS: Record<StatusInstancia, { variant: "success" | "error" | "neutral"; rotulo: string }> = {
  conectado: { variant: "success", rotulo: "Conectada" },
  erro: { variant: "error", rotulo: "Erro" },
  nao_conectado: { variant: "neutral", rotulo: "Não conectada" },
}

export function StatusBadge({ status }: { status: StatusInstancia }) {
  const { variant, rotulo } = BADGE_POR_STATUS[status]
  return <Badge variant={variant}>{rotulo}</Badge>
}
