import { CheckCircle2, CircleAlert, Hourglass, Package } from "lucide-react"
import { formatarNumero } from "@/lib/format"
import type { ProdutosDetalheContagem } from "@/lib/api/types"

export function MetricasGrid({ produtos }: { produtos: ProdutosDetalheContagem }) {
  const percentualCadastrado = produtos.total > 0 ? Math.round((produtos.cadastrados / produtos.total) * 100) : 0

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div className="flex flex-col justify-between gap-2 rounded-xl bg-card p-4">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="text-caption-medium">Produtos no espelho</span>
          <Package size={18} />
        </div>
        <div className="flex flex-col">
          <span className="text-mono-metric-lg font-mono text-foreground">{formatarNumero(produtos.total)}</span>
          <span className="mt-0.5 text-caption-label text-muted-foreground">Total sincronizado de fornecedores</span>
        </div>
      </div>

      <div className="flex flex-col justify-between gap-2 rounded-xl bg-card p-4">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="text-caption-medium">Cadastrados no Tiny</span>
          <CheckCircle2 size={18} className="text-success" />
        </div>
        <div className="flex flex-col">
          <span className="text-mono-metric-lg font-mono text-foreground">{formatarNumero(produtos.cadastrados)}</span>
          <span className="mt-0.5 text-caption-label text-success">{percentualCadastrado}% do espelho</span>
        </div>
      </div>

      <div className="flex flex-col justify-between gap-2 rounded-xl bg-card p-4">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="text-caption-medium">Aguardando estoque</span>
          <Hourglass size={18} />
        </div>
        <div className="flex flex-col">
          <span className="text-mono-metric-lg font-mono text-foreground">{formatarNumero(produtos.aguardando)}</span>
          <span className="mt-0.5 text-caption-label text-muted-foreground">zerados no fornecedor</span>
        </div>
      </div>

      <div className="flex flex-col justify-between gap-2 rounded-xl bg-card p-4">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="text-caption-medium">Com erro</span>
          <CircleAlert size={18} className="text-error" />
        </div>
        <div className="flex flex-col">
          <span className="text-mono-metric-lg font-mono text-error">{formatarNumero(produtos.com_erro)}</span>
          <span className="mt-0.5 text-caption-label text-error/80">falharam ao cadastrar</span>
        </div>
      </div>
    </div>
  )
}
