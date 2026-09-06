"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ui/empty-error-state"
import { ExecucoesTab } from "@/components/instancias/detalhe/execucoes-tab"
import { SeletorInstancia } from "./seletor-instancia"
import { useInstanciaSelecionada } from "./use-instancia-selecionada"

const COPY = {
  sincronizacoes: {
    titulo: "Sincronizações",
    subtitulo: "Histórico das rodadas de sincronização das instâncias, da mais recente para a mais antiga.",
  },
  logs: {
    titulo: "Logs",
    subtitulo: "Abra qualquer execução para inspecionar os logs detalhados — info, avisos e erros.",
  },
} as const

/**
 * Telas /sincronizacoes e /logs. As duas são a MESMA experiência da aba
 * Execuções da instância (`ExecucoesTab` — filtros, paginação server-side,
 * modal de logs), só que com um seletor de instância por cima. Sem lógica
 * nova: muda apenas a moldura de texto.
 */
export function ExecucoesGlobaisView({ variante }: { variante: keyof typeof COPY }) {
  const { titulo, subtitulo } = COPY[variante]
  const sel = useInstanciaSelecionada()

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-title-page text-foreground">{titulo}</h1>
          <p className="text-body-default text-muted-foreground">{subtitulo}</p>
        </div>
        {!sel.isLoading && !sel.isError && sel.instancias.length > 0 && (
          <SeletorInstancia instancias={sel.instancias} slug={sel.slug} onChange={sel.definir} />
        )}
      </div>

      {sel.isLoading && <Skeleton className="h-64 w-full rounded-xl" />}

      {sel.isError && (
        <div className="rounded-xl border border-border bg-card">
          <ErrorState title="Não foi possível carregar as instâncias." onRetry={sel.refetch} />
        </div>
      )}

      {sel.vazio && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card py-12 text-center">
          <p className="text-body-default text-foreground">Nenhuma instância cadastrada</p>
          <p className="max-w-sm text-caption-label text-muted-foreground">
            As sincronizações aparecem aqui depois que você cadastra e conecta uma instância.
          </p>
          <Button variant="primary" size="sm" asChild>
            <Link href="/instancias/novo">Criar instância</Link>
          </Button>
        </div>
      )}

      {!sel.isLoading && !sel.isError && sel.slug && <ExecucoesTab key={sel.slug} slug={sel.slug} />}
    </div>
  )
}
