import { cn } from "cn"
import type { InstanciaListagem } from "@/lib/api/types"

const FORNECEDORES: { chave: keyof InstanciaListagem["fornecedores"]; rotulo: string }[] = [
  { chave: "xbz", rotulo: "XBZ" },
  { chave: "asia", rotulo: "ASIA" },
  { chave: "somarcas", rotulo: "SOMAR" },
  { chave: "spot", rotulo: "SPOT" },
]

const CLASSES_POR_COR: Record<string, string> = {
  ok: "border-success/20 bg-success-subtle text-success",
  atencao: "border-warning/20 bg-warning-subtle text-warning",
  erro: "border-error/20 bg-error-subtle text-error",
  nao_configurado: "border-border bg-muted text-muted-foreground",
}

export function FornecedorPills({ fornecedores }: { fornecedores: InstanciaListagem["fornecedores"] }) {
  return (
    <div className="flex items-center gap-1">
      {FORNECEDORES.map(({ chave, rotulo }) => (
        <span
          key={chave}
          className={cn("rounded-sm border px-1 py-px text-code-inline", CLASSES_POR_COR[fornecedores[chave]])}
        >
          {rotulo}
        </span>
      ))}
    </div>
  )
}
