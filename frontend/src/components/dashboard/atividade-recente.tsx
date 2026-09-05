"use client"

import { StatusDot } from "@/components/ui/status-dot"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, ErrorState } from "@/components/ui/empty-error-state"
import { useAtividade } from "@/lib/api/hooks"
import { formatarDuracao, formatarTempoRelativo } from "@/lib/format"

const FORNECEDOR_ABREVIADO: Record<string, string> = {
  xbz: "XBZ",
  asia: "ASIA",
  somarcas: "SOMAR",
  spot: "SPOT",
}

const DOT_POR_STATUS: Record<string, "success" | "warning" | "error" | "neutral"> = {
  sucesso: "success",
  parcial: "warning",
  falha: "error",
  rodando: "neutral",
}

export function AtividadeRecente() {
  const { data: execucoes, isLoading, isError, refetch } = useAtividade(8)

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h2 className="text-header-section text-foreground">Atividade recente</h2>
      </div>
      <div className="divide-y divide-border-subtle">
        {isLoading &&
          Array.from({ length: 4 }).map((_, indice) => (
            <div key={indice} className="flex items-center gap-3 px-4 py-3">
              <Skeleton className="size-2 shrink-0 rounded-full" />
              <Skeleton className="h-4 flex-1" />
            </div>
          ))}

        {!isLoading && isError && (
          <ErrorState title="Não foi possível carregar a atividade recente." onRetry={() => refetch()} />
        )}

        {!isLoading && !isError && execucoes?.length === 0 && (
          <EmptyState title="Nenhuma execução ainda" description="As sincronizações aparecem aqui assim que rodarem." />
        )}

        {!isLoading &&
          !isError &&
          execucoes?.map((execucao) => (
            <div key={execucao.id} className="flex items-center gap-3 px-4 py-3">
              <StatusDot variant={DOT_POR_STATUS[execucao.status] ?? "neutral"} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-body-medium text-foreground">{execucao.instancia.nome}</span>
                  <span className="rounded-sm border border-border px-1 py-px text-code-inline text-muted-foreground">
                    {FORNECEDOR_ABREVIADO[execucao.fornecedor] ?? execucao.fornecedor}
                  </span>
                </div>
                <p className="truncate text-caption-label text-muted-foreground">
                  {execucao.total_lidos} lidos · {execucao.total_novos + execucao.total_atualizados} novos/atualizados ·{" "}
                  {execucao.total_erros} erros
                </p>
              </div>
              <span className="shrink-0 text-mono-metric text-muted-foreground">
                {formatarDuracao(execucao.duracao_segundos)}
              </span>
              <span className="shrink-0 text-caption-label text-muted-foreground">
                {formatarTempoRelativo(execucao.iniciada_em)}
              </span>
            </div>
          ))}
      </div>
    </div>
  )
}
