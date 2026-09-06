"use client"

import Link from "next/link"
import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import type { StatusInstancia } from "@/lib/api/types"

interface Props {
  busca: string
  onBuscaChange: (valor: string) => void
  status: StatusInstancia | ""
  onStatusChange: (valor: StatusInstancia | "") => void
}

export function InstanciasToolbar({ busca, onBuscaChange, status, onStatusChange }: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-1 flex-wrap items-center gap-2">
        <div className="relative min-w-[240px] max-w-sm flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={busca}
            onChange={(event) => onBuscaChange(event.target.value)}
            placeholder="Buscar por nome ou CNPJ"
            className="pl-8"
          />
        </div>
        <Select
          value={status || "todos"}
          onValueChange={(valor) => onStatusChange(valor === "todos" ? "" : (valor as StatusInstancia))}
        >
          <SelectTrigger>
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Status: Todos</SelectItem>
            <SelectItem value="conectado">Conectada</SelectItem>
            <SelectItem value="erro">Erro</SelectItem>
            <SelectItem value="nao_conectado">Não conectada</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button variant="primary" asChild>
        <Link href="/instancias/novo">Nova instância</Link>
      </Button>
    </div>
  )
}
