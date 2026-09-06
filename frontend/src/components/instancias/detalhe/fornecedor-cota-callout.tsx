import { AlertTriangle } from "lucide-react"

/** Só a XBZ tem cota diária (24 chamadas/dia) — ver CadenciaFornecedor.CADENCIA_MINIMA_XBZ_MINUTOS no backend. */
export function FornecedorCotaCallout() {
  return (
    <div className="mt-6 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-subtle p-3.5 text-caption-label text-warning">
      <AlertTriangle size={16} className="shrink-0" />
      <span>Este fornecedor permite no máximo 24 consultas por dia.</span>
    </div>
  )
}
