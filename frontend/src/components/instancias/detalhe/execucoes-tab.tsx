"use client"

import { useEffect, useState } from "react"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { PaginationFooter } from "@/components/instancias/pagination-footer"
import { useExecucoesInstancia } from "@/lib/api/hooks"
import { formatarNumero } from "@/lib/format"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { BADGE_POR_STATUS_EXECUCAO } from "./execucao-formato"
import { ExecucoesHistoricoTabela } from "./execucoes-historico-tabela"
import type { FornecedorEnum, StatusExecucao } from "@/lib/api/types"

const TAMANHO_PAGINA = 20

const FORNECEDORES: FornecedorEnum[] = ["xbz", "asia", "somarcas", "spot"]

const STATUS: StatusExecucao[] = ["rodando", "sucesso", "parcial", "falha"]

export function ExecucoesTab({ slug }: { slug: string }) {
  const [fornecedor, setFornecedor] = useState<FornecedorEnum | "">("")
  const [status, setStatus] = useState<StatusExecucao | "">("")
  const [pagina, setPagina] = useState(1)

  useEffect(() => {
    setPagina(1)
  }, [fornecedor, status])

  const { data, isLoading, isError, refetch, isFetching } = useExecucoesInstancia(slug, {
    fornecedor,
    status,
    page: pagina,
    pageSize: TAMANHO_PAGINA,
  })

  const total = data?.count ?? 0
  const totalPaginas = data ? Math.max(1, Math.ceil(data.count / TAMANHO_PAGINA)) : 1
  const temFiltros = Boolean(fornecedor || status)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-header-section text-foreground">Histórico de execuções</h2>
        <p className="text-caption-label text-muted-foreground">
          Todas as rodadas de sincronização desta instância, da mais recente para a mais antiga —
          {" "}
          {isLoading
            ? "carregando…"
            : `${formatarNumero(total)} ${total === 1 ? "execução" : "execuções"}`}
          .
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={fornecedor || "todos"}
          onValueChange={(valor) => setFornecedor(valor === "todos" ? "" : (valor as FornecedorEnum))}
        >
          <SelectTrigger>
            <SelectValue placeholder="Fornecedor" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Fornecedor: Todos</SelectItem>
            {FORNECEDORES.map((valor) => (
              <SelectItem key={valor} value={valor}>
                {ROTULO_FORNECEDOR[valor]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={status || "todos"}
          onValueChange={(valor) => setStatus(valor === "todos" ? "" : (valor as StatusExecucao))}
        >
          <SelectTrigger>
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Status: Todos</SelectItem>
            {STATUS.map((valor) => (
              <SelectItem key={valor} value={valor}>
                {BADGE_POR_STATUS_EXECUCAO[valor].rotulo}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <ExecucoesHistoricoTabela
        slug={slug}
        itens={data?.results ?? []}
        isLoading={isLoading}
        isError={isError}
        onRetry={() => refetch()}
        temFiltros={temFiltros}
      />

      {!isLoading && !isError && data && (
        <PaginationFooter
          pagina={pagina}
          totalPaginas={totalPaginas}
          totalItens={data.count}
          itensNaPagina={data.results.length}
          onPageChange={setPagina}
          rotuloItens="execuções"
        />
      )}

      {isFetching && !isLoading && (
        <p className="text-center text-caption-label text-muted-foreground">Atualizando…</p>
      )}
    </div>
  )
}
