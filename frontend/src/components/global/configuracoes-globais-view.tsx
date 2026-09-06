"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ui/empty-error-state"
import { ConfiguracoesTab } from "@/components/instancias/detalhe/configuracoes-tab"
import { SeletorInstancia } from "./seletor-instancia"
import { useInstanciaSelecionada } from "./use-instancia-selecionada"

/**
 * Tela /configuracoes — porta de entrada para as configurações das instâncias.
 * Uma instância → mostra as configurações dela direto; várias → seletor.
 * Reaproveita `ConfiguracoesTab` (config do Tiny + cadências), sem mudar
 * nenhuma regra.
 */
export function ConfiguracoesGlobaisView() {
  const sel = useInstanciaSelecionada()

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-title-page text-foreground">Configurações</h1>
          <p className="text-body-default text-muted-foreground">
            {sel.unica
              ? "Configurações operacionais da instância."
              : "Escolha uma instância para ver e editar suas configurações."}
          </p>
        </div>
        {!sel.isLoading && !sel.isError && sel.instancias.length > 0 && (
          <SeletorInstancia instancias={sel.instancias} slug={sel.slug} onChange={sel.definir} />
        )}
      </div>

      {sel.isLoading && (
        <div className="flex flex-col gap-6">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      )}

      {sel.isError && (
        <div className="rounded-xl border border-border bg-card">
          <ErrorState title="Não foi possível carregar as instâncias." onRetry={sel.refetch} />
        </div>
      )}

      {sel.vazio && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card py-12 text-center">
          <p className="text-body-default text-foreground">Nenhuma instância cadastrada</p>
          <p className="max-w-sm text-caption-label text-muted-foreground">
            Cadastre uma instância para configurar origem/unidade padrão do Tiny e a cadência dos fornecedores.
          </p>
          <Button variant="primary" size="sm" asChild>
            <Link href="/instancias/novo">Criar instância</Link>
          </Button>
        </div>
      )}

      {!sel.isLoading && !sel.isError && sel.slug && <ConfiguracoesTab key={sel.slug} slug={sel.slug} />}
    </div>
  )
}
