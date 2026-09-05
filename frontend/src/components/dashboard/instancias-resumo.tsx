"use client"

import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { StatusDot } from "@/components/ui/status-dot"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, ErrorState } from "@/components/ui/empty-error-state"
import { useInstanciasListagem } from "@/lib/api/hooks"
import { formatarNumero } from "@/lib/format"
import type { StatusInstancia } from "@/lib/api/types"

const DOT_POR_STATUS: Record<StatusInstancia, "success" | "warning" | "error" | "neutral"> = {
  conectado: "success",
  erro: "error",
  nao_conectado: "neutral",
}

const BADGE_POR_STATUS: Record<StatusInstancia, { variant: "success" | "error" | "neutral"; rotulo: string }> = {
  conectado: { variant: "success", rotulo: "Conectada" },
  erro: { variant: "error", rotulo: "Erro" },
  nao_conectado: { variant: "neutral", rotulo: "Não conectada" },
}

export function InstanciasResumo() {
  const { data, isLoading, isError, refetch } = useInstanciasListagem({ pageSize: 5 })

  return (
    <div className="flex flex-col rounded-xl border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h2 className="text-header-section text-foreground">Instâncias</h2>
      </div>
      <div className="divide-y divide-border-subtle">
        {isLoading &&
          Array.from({ length: 4 }).map((_, indice) => (
            <div key={indice} className="flex items-center gap-3 px-4 py-3">
              <Skeleton className="size-2 shrink-0 rounded-full" />
              <Skeleton className="h-4 flex-1" />
            </div>
          ))}

        {!isLoading && isError && <ErrorState title="Não foi possível carregar as instâncias." onRetry={() => refetch()} />}

        {!isLoading && !isError && data?.results.length === 0 && <EmptyState title="Nenhuma instância cadastrada" />}

        {!isLoading &&
          !isError &&
          data?.results.map((instancia) => (
            <Link
              key={instancia.slug}
              href={`/instancias/${instancia.slug}`}
              className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-accent"
            >
              <StatusDot variant={DOT_POR_STATUS[instancia.status]} />
              <span className="min-w-0 flex-1 truncate text-body-medium text-foreground">{instancia.nome}</span>
              <Badge variant={BADGE_POR_STATUS[instancia.status].variant}>
                {BADGE_POR_STATUS[instancia.status].rotulo}
              </Badge>
              <span className="shrink-0 text-mono-metric text-muted-foreground">
                {formatarNumero(instancia.produtos.total)}
              </span>
            </Link>
          ))}
      </div>
      {!isLoading && !isError && data && data.count > 0 && (
        <div className="border-t border-border px-4 py-3">
          <Link href="/instancias" className="text-caption-label text-primary hover:underline">
            Ver todas as {formatarNumero(data.count)} instâncias
          </Link>
        </div>
      )}
    </div>
  )
}
