import { ConfiguracoesTinyCard } from "./configuracoes-tiny-card"
import { ConfiguracoesCadenciasCard } from "./configuracoes-cadencias-card"

export function ConfiguracoesTab({ slug }: { slug: string }) {
  return (
    <div className="flex flex-col gap-6">
      <ConfiguracoesTinyCard slug={slug} />
      <ConfiguracoesCadenciasCard slug={slug} />
    </div>
  )
}
