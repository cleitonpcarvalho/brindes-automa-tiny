"use client"

import { Loader2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { formatarNumero } from "@/lib/format"
import type { RetentativaLote } from "@/lib/api/types"

/**
 * Barra de ação/progresso da retentativa EM LOTE, acima da tabela, quando o
 * filtro "Erros" está ativo. Enquanto um job está `rodando`, mostra o
 * progresso (processados/total · sucessos · erros) e o botão fica escondido.
 */
export function RetentarLoteBarra({
  qtdErrosTotal,
  qtdSelecionada,
  selecaoTodos,
  progresso,
  disparando,
  onSelecionarTodos,
  onLimpar,
  onDisparar,
}: {
  qtdErrosTotal: number
  qtdSelecionada: number
  selecaoTodos: boolean
  progresso: RetentativaLote | null | undefined
  disparando: boolean
  onSelecionarTodos: () => void
  onLimpar: () => void
  onDisparar: () => void
}) {
  if (progresso?.status === "rodando") {
    const total = progresso.total ?? 0
    const processados = progresso.processados ?? 0
    const sucessos = progresso.sucessos ?? 0
    const erros = progresso.erros ?? 0
    const ignorados = progresso.ignorados ?? 0
    const pct = total ? Math.round((processados / total) * 100) : 0
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-caption-medium">
          <span className="flex items-center gap-2 text-foreground">
            <Loader2 size={14} className="animate-spin" />
            Retentativa em lote em andamento
          </span>
          <span className="text-muted-foreground">
            {formatarNumero(processados)}/{formatarNumero(total)} ·{" "}
            <span className="text-success">{formatarNumero(sucessos)} ok</span> ·{" "}
            <span className="text-error">{formatarNumero(erros)} erro</span>
            {ignorados > 0 && ` · ${formatarNumero(ignorados)} já cadastrado`}
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-background">
          <div
            className="h-full rounded-full bg-primary transition-[width]"
            style={{ width: `${pct}%` }}
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
      </div>
    )
  }

  const temSelecao = selecaoTodos || qtdSelecionada > 0

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/40 px-4 py-2.5">
      <span className="text-caption-medium text-foreground">
        {temSelecao
          ? selecaoTodos
            ? `Todos os ${formatarNumero(qtdErrosTotal)} erros selecionados`
            : `${formatarNumero(qtdSelecionada)} selecionado${qtdSelecionada === 1 ? "" : "s"}`
          : `${formatarNumero(qtdErrosTotal)} SKU${qtdErrosTotal === 1 ? "" : "s"} com erro`}
      </span>

      {!selecaoTodos && qtdErrosTotal > qtdSelecionada && (
        <Button variant="ghost" size="sm" onClick={onSelecionarTodos}>
          Selecionar todos os {formatarNumero(qtdErrosTotal)} erros da execução
        </Button>
      )}

      {temSelecao && (
        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onLimpar}>
            Limpar
          </Button>
          <Button variant="secondary" size="sm" onClick={onDisparar} disabled={disparando}>
            {disparando ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Tentar novamente selecionados ({formatarNumero(selecaoTodos ? qtdErrosTotal : qtdSelecionada)})
          </Button>
        </div>
      )}
    </div>
  )
}
