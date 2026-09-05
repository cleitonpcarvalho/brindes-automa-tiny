"use client"

import { cn } from "cn"
import type { Periodo } from "@/lib/api/types"

const OPCOES: { valor: Periodo; rotulo: string }[] = [
  { valor: "hoje", rotulo: "Hoje" },
  { valor: "7d", rotulo: "7 dias" },
  { valor: "30d", rotulo: "30 dias" },
]

export function PeriodSelector({ valor, onChange }: { valor: Periodo; onChange: (periodo: Periodo) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-0.5">
      {OPCOES.map((opcao) => (
        <button
          key={opcao.valor}
          type="button"
          onClick={() => onChange(opcao.valor)}
          className={cn(
            "rounded-md px-2.5 py-1 text-caption-medium transition-colors",
            valor === opcao.valor
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {opcao.rotulo}
        </button>
      ))}
    </div>
  )
}
