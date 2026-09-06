import type { CorFornecedor, FornecedorEnum } from "@/lib/api/types"

export const CLASSES_BADGE_POR_COR: Record<CorFornecedor, string> = {
  ok: "border-success/20 bg-success-subtle text-success",
  atencao: "border-warning/20 bg-warning-subtle text-warning",
  erro: "border-error/20 bg-error-subtle text-error",
  nao_configurado: "border-border bg-muted text-muted-foreground",
}

export const DOT_POR_COR: Record<CorFornecedor, string> = {
  ok: "bg-success",
  atencao: "bg-warning",
  erro: "bg-error",
  nao_configurado: "bg-muted-foreground",
}

export const ROTULO_POR_COR: Record<CorFornecedor, string> = {
  ok: "Conectado",
  atencao: "Atenção",
  erro: "Falha",
  nao_configurado: "Não configurado",
}

export const ROTULO_FORNECEDOR: Record<FornecedorEnum, string> = {
  xbz: "XBZ",
  asia: "Asia Import",
  somarcas: "Só Marcas",
  spot: "Spot Gifts",
}
