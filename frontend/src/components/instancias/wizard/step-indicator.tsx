import { Check } from "lucide-react"
import { cn } from "cn"

const PASSOS = [
  { numero: 1, rotulo: "Identificação" },
  { numero: 2, rotulo: "Credenciais" },
  { numero: 3, rotulo: "Autorização" },
  { numero: 4, rotulo: "Fornecedores" },
] as const

/** design/04-instancia-nova — os 4 círculos com linhas entre eles. */
export function StepIndicator({ passoAtual }: { passoAtual: 1 | 2 | 3 | 4 }) {
  return (
    <div className="mb-8 flex items-center justify-between select-none">
      {PASSOS.map((passo, indice) => {
        const concluido = passo.numero < passoAtual
        const ativo = passo.numero === passoAtual
        return (
          <div key={passo.numero} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full text-caption-medium",
                  concluido && "border border-primary/40 bg-primary/15 text-primary",
                  ativo && "bg-primary font-semibold text-primary-foreground shadow-sm",
                  !concluido && !ativo && "border border-border bg-card text-muted-foreground"
                )}
              >
                {concluido ? <Check size={14} /> : passo.numero}
              </div>
              <span
                className={cn(
                  "text-caption-medium whitespace-nowrap",
                  ativo ? "font-semibold text-foreground" : "text-muted-foreground"
                )}
              >
                {passo.numero}. {passo.rotulo}
              </span>
            </div>
            {indice < PASSOS.length - 1 && <div className="mx-3 h-px flex-1 bg-border" />}
          </div>
        )
      })}
    </div>
  )
}
