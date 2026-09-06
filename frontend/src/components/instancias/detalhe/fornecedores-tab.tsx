"use client"

import { Lock } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ui/empty-error-state"
import { useCadencias, useCredenciais } from "@/lib/api/hooks"
import { FornecedorAcordeao } from "./fornecedor-acordeao"
import type { InstanciaDetalhe } from "@/lib/api/types"

export function FornecedoresTab({ instancia, slug }: { instancia: InstanciaDetalhe; slug: string }) {
  const credenciais = useCredenciais(slug)
  const cadencias = useCadencias(slug)

  if (credenciais.isLoading || cadencias.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        {Array.from({ length: 4 }).map((_, indice) => (
          <Skeleton key={indice} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  if (credenciais.isError || cadencias.isError || !credenciais.data || !cadencias.data) {
    return <ErrorState onRetry={() => { credenciais.refetch(); cadencias.refetch(); }} />
  }

  return (
    <div className="flex flex-col gap-4">
      {instancia.fornecedores.map((statusDetalhe, indice) => {
        const credencial = credenciais.data.find((c) => c.fornecedor === statusDetalhe.fornecedor)!
        const cadencia = cadencias.data.find((c) => c.fornecedor === statusDetalhe.fornecedor)!
        const ultimaExecucao = instancia.ultimas_execucoes.find(
          (execucao) =>
            execucao.fornecedor === statusDetalhe.fornecedor && execucao.iniciada_em === statusDetalhe.ultima_execucao_em
        )

        return (
          <FornecedorAcordeao
            key={statusDetalhe.fornecedor}
            statusDetalhe={statusDetalhe}
            credencial={credencial}
            cadencia={cadencia}
            mensagemErroUltimaExecucao={ultimaExecucao?.mensagem_erro}
            slug={slug}
            defaultExpanded={indice === 0}
          />
        )
      })}

      <footer className="mt-2 flex items-center gap-2 text-caption-label text-muted-foreground">
        <Lock size={14} className="shrink-0" />
        <span>As credenciais são armazenadas criptografadas e nunca são exibidas por completo.</span>
      </footer>
    </div>
  )
}
