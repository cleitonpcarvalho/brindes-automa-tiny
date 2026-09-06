"use client"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import type { InstanciaListagem } from "@/lib/api/types"

interface Props {
  instancias: InstanciaListagem[]
  slug: string
  onChange: (slug: string) => void
}

/**
 * Seletor da instância ativa nas telas globais. Uma só instância → rótulo
 * estático (não há o que escolher). Várias → um Select claro.
 */
export function SeletorInstancia({ instancias, slug, onChange }: Props) {
  if (instancias.length <= 1) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-caption-label tracking-wider text-muted-foreground uppercase">Instância</span>
        <span className="rounded-lg border border-border bg-card px-2.5 py-1 text-body-medium text-foreground">
          {instancias[0]?.nome ?? "—"}
        </span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-caption-label tracking-wider text-muted-foreground uppercase">Instância</span>
      <Select value={slug} onValueChange={onChange}>
        <SelectTrigger className="min-w-[220px]">
          <SelectValue placeholder="Escolha uma instância" />
        </SelectTrigger>
        <SelectContent>
          {instancias.map((instancia) => (
            <SelectItem key={instancia.slug} value={instancia.slug}>
              {instancia.nome}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
