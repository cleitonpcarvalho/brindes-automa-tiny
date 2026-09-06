"use client"

import { useState } from "react"
import { AlertTriangle, ChevronDown, ChevronUp, RefreshCw } from "lucide-react"
import { cn } from "cn"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useSincronizarFornecedor } from "@/lib/api/hooks"
import { formatarNumero, formatarTempoRelativo } from "@/lib/format"
import { DOT_POR_COR, ROTULO_FORNECEDOR, ROTULO_POR_COR } from "../cor-fornecedor"
import { FornecedorCredenciaisForm } from "./fornecedor-credenciais-form"
import { FornecedorCadenciaForm } from "./fornecedor-cadencia-form"
import { FornecedorCotaCallout } from "./fornecedor-cota-callout"
import type { CadenciaFornecedor, CredencialFornecedorResposta, FornecedorDetalhe } from "@/lib/api/types"

const VARIANTE_BADGE_POR_COR = {
  ok: "success",
  atencao: "warning",
  erro: "error",
  nao_configurado: "neutral",
} as const

interface Props {
  statusDetalhe: FornecedorDetalhe
  credencial: CredencialFornecedorResposta
  cadencia: CadenciaFornecedor
  mensagemErroUltimaExecucao?: string
  slug: string
  defaultExpanded?: boolean
}

export function FornecedorAcordeao({
  statusDetalhe,
  credencial,
  cadencia,
  mensagemErroUltimaExecucao,
  slug,
  defaultExpanded = false,
}: Props) {
  const [expandido, setExpandido] = useState(defaultExpanded)
  const sincronizar = useSincronizarFornecedor(slug, statusDetalhe.fornecedor)
  const fornecedor = statusDetalhe.fornecedor

  const descricao = statusDetalhe.ultima_execucao_em
    ? `${statusDetalhe.ultima_execucao_status === "falha" ? "falha " : ""}${formatarTempoRelativo(statusDetalhe.ultima_execucao_em)} · ${formatarNumero(statusDetalhe.produtos_total)} produtos sincronizados · intervalo ${cadencia.intervalo_minutos ?? 60}min`
    : "ainda sem execuções"

  return (
    <article className="overflow-hidden rounded-xl bg-card">
      <div
        className="flex cursor-pointer items-center justify-between p-4 transition-colors hover:bg-secondary/50"
        onClick={() => setExpandido((atual) => !atual)}
      >
        <div className="flex items-center gap-3">
          <span className="relative flex size-2.5">
            {statusDetalhe.cor === "ok" && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-75" />
            )}
            <span className={cn("relative inline-flex size-2.5 rounded-full", DOT_POR_COR[statusDetalhe.cor])} />
          </span>
          <h2 className="text-body-medium font-semibold text-foreground">{ROTULO_FORNECEDOR[fornecedor]}</h2>
          <Badge variant={VARIANTE_BADGE_POR_COR[statusDetalhe.cor]}>{ROTULO_POR_COR[statusDetalhe.cor]}</Badge>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-caption-label text-muted-foreground">{descricao}</span>
          <Button
            variant="secondary"
            size="sm"
            onClick={(event) => {
              event.stopPropagation()
              sincronizar.mutate()
            }}
            disabled={!statusDetalhe.credencial_ativa || sincronizar.isPending}
          >
            <RefreshCw size={14} className={sincronizar.isPending ? "animate-spin" : undefined} />
            Sincronizar
          </Button>
          <button
            type="button"
            aria-label={expandido ? "Recolher detalhes" : "Expandir detalhes"}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            {expandido ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {!expandido && statusDetalhe.cor === "erro" && mensagemErroUltimaExecucao && (
        <div className="flex items-center gap-2 border-t border-error/20 bg-error-subtle px-4 py-2.5 text-caption-medium text-error">
          <AlertTriangle size={14} className="shrink-0" />
          <span>Falha na última execução · {mensagemErroUltimaExecucao}</span>
        </div>
      )}

      {expandido && (
        <div className="border-t border-border p-6">
          <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
            <FornecedorCredenciaisForm fornecedor={fornecedor} credencial={credencial} slug={slug} />
            <FornecedorCadenciaForm fornecedor={fornecedor} cadencia={cadencia} slug={slug} />
          </div>
          {fornecedor === "xbz" && <FornecedorCotaCallout />}
        </div>
      )}
    </article>
  )
}
