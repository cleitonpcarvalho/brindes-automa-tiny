import { cn } from "cn"
import { Badge } from "@/components/ui/badge"

type CorProgresso = "primary" | "success" | "warning" | "error"

interface MetricCardProps {
  titulo: string
  valor: string
  comparacao?: string
  comparacaoVariant?: "success" | "warning" | "error" | "neutral"
  progresso?: number
  progressoVariant?: CorProgresso
}

const COR_BARRA: Record<CorProgresso, string> = {
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
}

export function MetricCard({
  titulo,
  valor,
  comparacao,
  comparacaoVariant = "neutral",
  progresso,
  progressoVariant = "primary",
}: MetricCardProps) {
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-card p-4">
      <span className="text-caption-label text-muted-foreground">{titulo}</span>
      <span className="text-mono-metric-lg text-foreground">{valor}</span>
      {comparacao && (
        <Badge variant={comparacaoVariant} className="w-fit">
          {comparacao}
        </Badge>
      )}
      {progresso !== undefined && (
        <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full transition-[width]", COR_BARRA[progressoVariant])}
            style={{ width: `${Math.min(100, Math.max(0, progresso))}%` }}
          />
        </div>
      )}
    </div>
  )
}
