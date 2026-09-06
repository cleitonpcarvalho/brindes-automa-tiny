import { ConexaoCard } from "./conexao-card"
import { MetricasGrid } from "./metricas-grid"
import { FornecedoresResumoCard } from "./fornecedores-resumo-card"
import { CadenciaCard } from "./cadencia-card"
import { ExecucoesTabela } from "./execucoes-tabela"
import type { InstanciaDetalhe } from "@/lib/api/types"

export function VisaoGeralTab({ instancia, slug }: { instancia: InstanciaDetalhe; slug: string }) {
  return (
    <div className="flex flex-col gap-6">
      <ConexaoCard instancia={instancia} slug={slug} />
      <MetricasGrid produtos={instancia.produtos} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <FornecedoresResumoCard fornecedores={instancia.fornecedores} slug={slug} />
        <CadenciaCard cadencias={instancia.cadencias} fornecedores={instancia.fornecedores} />
      </div>
      <ExecucoesTabela execucoes={instancia.ultimas_execucoes} />
    </div>
  )
}
