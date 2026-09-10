import { Suspense, use } from "react"
import { ExecucaoDetalheView } from "@/components/instancias/detalhe/execucao-detalhe-view"

/** Auditoria estruturada de uma execução: resumo + tabela por SKU + logs técnicos. */
export default function ExecucaoDetalhePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; id: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const { slug, id } = use(params)
  const query = new URLSearchParams()
  Object.entries(use(searchParams)).forEach(([chave, valor]) => {
    if (typeof valor === "string") query.set(chave, valor)
  })

  return (
    <Suspense>
      <ExecucaoDetalheView slug={slug} execucaoId={id} queryInicial={query.toString()} />
    </Suspense>
  )
}
