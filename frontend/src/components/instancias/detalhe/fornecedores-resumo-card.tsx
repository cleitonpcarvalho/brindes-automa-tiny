"use client"

import { RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useSincronizarFornecedor } from "@/lib/api/hooks"
import { formatarNumero, formatarTempoRelativo } from "@/lib/format"
import { DOT_POR_COR, ROTULO_FORNECEDOR } from "../cor-fornecedor"
import type { FornecedorDetalhe } from "@/lib/api/types"

function LinhaFornecedor({ fornecedor, slug }: { fornecedor: FornecedorDetalhe; slug: string }) {
  const sincronizar = useSincronizarFornecedor(slug, fornecedor.fornecedor)

  const descricao = fornecedor.ultima_execucao_em
    ? `${fornecedor.ultima_execucao_status === "falha" ? "falha " : ""}${formatarTempoRelativo(fornecedor.ultima_execucao_em)} · ${formatarNumero(fornecedor.produtos_total)} produtos`
    : fornecedor.credencial_configurada
      ? "ainda sem execuções"
      : "credencial não configurada"

  return (
    <div className="flex items-center justify-between rounded bg-secondary p-2 transition-colors hover:bg-accent">
      <div className="flex items-center gap-3">
        <span className={`size-2 rounded-full ${DOT_POR_COR[fornecedor.cor]}`} />
        <div className="flex flex-col">
          <span className="text-body-medium text-foreground">{ROTULO_FORNECEDOR[fornecedor.fornecedor]}</span>
          <span className={`text-caption-label ${fornecedor.cor === "erro" ? "text-error" : "text-muted-foreground"}`}>
            {descricao}
          </span>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => sincronizar.mutate()}
        disabled={!fornecedor.credencial_ativa || sincronizar.isPending}
      >
        <RefreshCw size={14} className={sincronizar.isPending ? "animate-spin" : undefined} />
        Sincronizar
      </Button>
    </div>
  )
}

export function FornecedoresResumoCard({ fornecedores, slug }: { fornecedores: FornecedorDetalhe[]; slug: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl bg-card p-4 lg:col-span-7">
      <div className="flex items-center justify-between pb-1">
        <div>
          <h2 className="text-header-section text-foreground">Fornecedores desta instância</h2>
          <p className="text-caption-label text-muted-foreground">Mapeamentos de catálogo em execução</p>
        </div>
      </div>
      <div className="flex flex-col gap-1">
        {fornecedores.map((fornecedor) => (
          <LinhaFornecedor key={fornecedor.fornecedor} fornecedor={fornecedor} slug={slug} />
        ))}
      </div>
    </div>
  )
}
