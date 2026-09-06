"use client"

import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ui/empty-error-state"
import { useCadencias } from "@/lib/api/hooks"
import { formatarTempoAte } from "@/lib/format"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { FornecedorCadenciaForm } from "./fornecedor-cadencia-form"
import type { FornecedorEnum } from "@/lib/api/types"

const FORNECEDORES: FornecedorEnum[] = ["xbz", "asia", "somarcas", "spot"]

export function ConfiguracoesCadenciasCard({ slug }: { slug: string }) {
  const { data, isLoading, isError, refetch } = useCadencias(slug)

  return (
    <section className="flex flex-col gap-4 rounded-xl bg-card p-4">
      <div>
        <h2 className="text-header-section text-foreground">Cadência dos fornecedores</h2>
        <p className="text-caption-label text-muted-foreground">
          De quanto em quanto tempo cada fornecedor é sincronizado automaticamente. Salvar aqui só grava a
          configuração — não dispara sincronização.
        </p>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {FORNECEDORES.map((f) => (
            <Skeleton key={f} className="h-40 w-full rounded-lg" />
          ))}
        </div>
      )}

      {isError && <ErrorState onRetry={() => refetch()} />}

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {FORNECEDORES.map((fornecedor) => {
            const cadencia = data.find((c) => c.fornecedor === fornecedor)
            if (!cadencia) return null
            return (
              <div key={fornecedor} className="flex flex-col gap-3 rounded-lg border border-border p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-body-medium text-foreground">{ROTULO_FORNECEDOR[fornecedor]}</span>
                  {cadencia.ativo && cadencia.proxima_execucao_em && (
                    <span className="text-caption-label text-muted-foreground">
                      próxima {formatarTempoAte(cadencia.proxima_execucao_em)}
                    </span>
                  )}
                </div>
                <FornecedorCadenciaForm fornecedor={fornecedor} cadencia={cadencia} slug={slug} />
                {fornecedor === "xbz" && (
                  <p className="text-caption-label text-muted-foreground">
                    Mínimo de 1 hora — a XBZ limita a 24 chamadas por dia.
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
