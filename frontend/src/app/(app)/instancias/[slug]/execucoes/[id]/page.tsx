import { Suspense, use } from "react"
import { ExecucaoDetalheView } from "@/components/instancias/detalhe/execucao-detalhe-view"

/** Auditoria estruturada de uma execução: resumo + tabela por SKU + logs técnicos. */
export default function ExecucaoDetalhePage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>
}) {
  const { slug, id } = use(params)

  return (
    <Suspense>
      <ExecucaoDetalheView slug={slug} execucaoId={id} />
    </Suspense>
  )
}
