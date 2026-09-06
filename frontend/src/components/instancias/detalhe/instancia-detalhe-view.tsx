"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { ArrowLeft, CheckCircle2 } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ui/empty-error-state"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { StatusBadge } from "@/components/instancias/status-badge"
import { useInstancia } from "@/lib/api/hooks"
import { VisaoGeralTab } from "./visao-geral-tab"
import { FornecedoresTab } from "./fornecedores-tab"
import { ProdutosTab } from "./produtos-tab"
import { ExecucoesTab } from "./execucoes-tab"
import { ConfiguracoesTab } from "./configuracoes-tab"

export function InstanciaDetalheView({ slug }: { slug: string }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const autorizado = searchParams.get("autorizado") === "1"

  const [aba, setAba] = useState(autorizado ? "fornecedores" : "visao-geral")
  const [mostrarBannerSucesso, setMostrarBannerSucesso] = useState(autorizado)

  const { data: instancia, isLoading, isError, refetch } = useInstancia(slug)

  useEffect(() => {
    if (autorizado) {
      router.replace(`/instancias/${slug}`)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <Link
        href="/instancias"
        className="flex w-fit items-center gap-1.5 text-caption-label text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Voltar para instâncias
      </Link>

      <div className="flex flex-col gap-1 border-b border-border pb-4">
        <div className="flex flex-wrap items-center gap-3">
          {isLoading ? (
            <Skeleton className="h-8 w-64" />
          ) : (
            <h1 className="text-title-page text-foreground">{instancia?.nome ?? slug}</h1>
          )}
          {instancia?.cnpj && (
            <span className="rounded bg-muted px-2 py-0.5 font-mono text-code-inline text-muted-foreground">
              {instancia.cnpj}
            </span>
          )}
          {instancia && <StatusBadge status={instancia.status} />}
        </div>
      </div>

      {mostrarBannerSucesso && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-success/20 bg-success-subtle px-4 py-3 text-body-default text-success">
          <span className="flex items-center gap-2">
            <CheckCircle2 size={16} />
            Instância autorizada com sucesso! Configure as credenciais dos fornecedores abaixo.
          </span>
          <button
            type="button"
            onClick={() => setMostrarBannerSucesso(false)}
            className="text-caption-label text-success/80 hover:underline"
          >
            Dispensar
          </button>
        </div>
      )}

      {isLoading && <Skeleton className="h-64 w-full rounded-xl" />}
      {isError && <ErrorState onRetry={() => refetch()} />}

      {instancia && (
        <Tabs value={aba} onValueChange={setAba}>
          <TabsList>
            <TabsTrigger value="visao-geral">Visão geral</TabsTrigger>
            <TabsTrigger value="fornecedores">Fornecedores</TabsTrigger>
            <TabsTrigger value="produtos">Produtos</TabsTrigger>
            <TabsTrigger value="execucoes">Execuções</TabsTrigger>
            <TabsTrigger value="configuracoes">Configurações</TabsTrigger>
          </TabsList>

          <TabsContent value="visao-geral">
            <VisaoGeralTab instancia={instancia} slug={slug} />
          </TabsContent>

          <TabsContent value="fornecedores">
            <FornecedoresTab instancia={instancia} slug={slug} />
          </TabsContent>

          <TabsContent value="produtos">
            <ProdutosTab slug={slug} />
          </TabsContent>

          <TabsContent value="execucoes">
            <ExecucoesTab slug={slug} />
          </TabsContent>

          <TabsContent value="configuracoes">
            <ConfiguracoesTab slug={slug} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
