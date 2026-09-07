import { Suspense, use } from "react"
import { VariacaoDetalheView } from "@/components/instancias/detalhe/variacao-detalhe-view"

/** Detalhe somente leitura de uma variação (SKU) do espelho local. */
export default function VariacaoDetalhePage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>
}) {
  const { slug, id } = use(params)

  return (
    <Suspense>
      <VariacaoDetalheView slug={slug} variacaoId={id} />
    </Suspense>
  )
}
