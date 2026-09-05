import { StatusDot } from "@/components/ui/status-dot"

const ITENS: { variant: "success" | "warning" | "error" | "neutral"; rotulo: string }[] = [
  { variant: "success", rotulo: "Sincronizado recentemente" },
  { variant: "warning", rotulo: "Atenção" },
  { variant: "error", rotulo: "Falha" },
  { variant: "neutral", rotulo: "Não configurado" },
]

export function StatusLegend() {
  return (
    <div className="flex flex-wrap items-center gap-3 text-caption-label text-muted-foreground">
      <span>Legenda:</span>
      {ITENS.map((item) => (
        <span key={item.rotulo} className="flex items-center gap-1.5">
          <StatusDot variant={item.variant} />
          {item.rotulo}
        </span>
      ))}
    </div>
  )
}
