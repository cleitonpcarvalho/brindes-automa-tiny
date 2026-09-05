import { StatusLegend } from "./status-legend"
import { formatarNumero } from "@/lib/format"

export function StatusStrip({ total }: { total: number }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
      <span className="text-body-medium text-foreground">{formatarNumero(total)} instâncias</span>
      <StatusLegend />
    </div>
  )
}
