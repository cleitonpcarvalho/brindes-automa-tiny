import { Suspense, use } from "react"
import { VariacaoDetalheView } from "@/components/instancias/detalhe/variacao-detalhe-view"

/** Detalhe somente leitura de uma variação (SKU) do espelho local. */
export default function VariacaoDetalhePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; id: string }>
  searchParams: Promise<{ retorno?: string | string[] }>
}) {
  const { slug, id } = use(params)
  const { retorno } = use(searchParams)

  return (
    <Suspense>
      <VariacaoDetalheView slug={slug} variacaoId={id} retorno={typeof retorno === "string" ? retorno : undefined} />
    </Suspense>
  )
}
