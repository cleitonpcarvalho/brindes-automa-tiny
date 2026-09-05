"use client"

import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { StatusDot } from "@/components/ui/status-dot"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, ErrorState } from "@/components/ui/empty-error-state"
import { useAlertas } from "@/lib/api/hooks"
import { formatarTempoRelativo } from "@/lib/format"
import type { Alerta } from "@/lib/api/types"

const FORNECEDOR_ABREVIADO: Record<string, string> = {
  xbz: "XBZ",
  asia: "ASIA",
  somarcas: "SOMAR",
  spot: "SPOT",
}

export function AlertasPanel() {
  const { data: alertas, isLoading, isError, refetch } = useAlertas()

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <h2 className="text-header-section text-foreground">Precisam da sua atenção</h2>
        {!isLoading && !isError && alertas && alertas.length > 0 && <Badge variant="warning">{alertas.length}</Badge>}
      </div>

      <div className="divide-y divide-border-subtle">
        {isLoading &&
          Array.from({ length: 3 }).map((_, indice) => (
            <div key={indice} className="flex items-center gap-3 px-4 py-3">
              <Skeleton className="size-2.5 shrink-0 rounded-full" />
              <Skeleton className="h-4 flex-1" />
            </div>
          ))}

        {!isLoading && isError && <ErrorState title="Não foi possível carregar os alertas." onRetry={() => refetch()} />}

        {!isLoading && !isError && alertas?.length === 0 && (
          <EmptyState title="Nenhum alerta aberto" description="Tudo sincronizando normalmente." />
        )}

        {!isLoading &&
          !isError &&
          alertas?.map((alerta: Alerta) => (
            <div key={alerta.id} className="flex items-center gap-3 px-4 py-3">
              <StatusDot variant={alerta.severidade === "critica" ? "error" : "warning"} ring />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-body-medium text-foreground">{alerta.instancia.nome}</span>
                  {alerta.fornecedor && (
                    <span className="rounded-sm border border-border px-1 py-px text-code-inline text-muted-foreground">
                      {FORNECEDOR_ABREVIADO[alerta.fornecedor] ?? alerta.fornecedor}
                    </span>
                  )}
                </div>
                <p className="truncate text-caption-label text-muted-foreground">{alerta.mensagem}</p>
              </div>
              <span className="shrink-0 text-caption-label text-muted-foreground">
                {formatarTempoRelativo(alerta.momento)}
              </span>
              <Button variant="secondary" size="sm" asChild>
                <Link href={`/instancias/${alerta.instancia.slug}`}>{alerta.acao_sugerida.rotulo}</Link>
              </Button>
            </div>
          ))}
      </div>
    </div>
  )
}
