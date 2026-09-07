"use client"

import { useEffect, useState } from "react"
import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { PaginationFooter } from "@/components/instancias/pagination-footer"
import { useProdutosInstancia } from "@/lib/api/hooks"
import { formatarNumero } from "@/lib/format"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { ProdutosTabela } from "./produtos-tabela"
import { ROTULO_STATUS_VARIACAO } from "./variacao-status"
import type { FornecedorEnum, StatusVariacao } from "@/lib/api/types"

const TAMANHO_PAGINA = 20

const FORNECEDORES: FornecedorEnum[] = ["xbz", "asia", "somarcas", "spot"]

export function ProdutosTab({ slug }: { slug: string }) {
  const [buscaInput, setBuscaInput] = useState("")
  const [busca, setBusca] = useState("")
  const [fornecedor, setFornecedor] = useState<FornecedorEnum | "">("")
  const [status, setStatus] = useState<StatusVariacao | "">("")
  const [pagina, setPagina] = useState(1)

  // Debounce simples: não dispara uma consulta a cada tecla (mesmo padrão da
  // listagem de instâncias).
  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaInput), 300)
    return () => clearTimeout(temporizador)
  }, [buscaInput])

  useEffect(() => {
    setPagina(1)
  }, [busca, fornecedor, status])

  const { data, isLoading, isError, refetch, isFetching } = useProdutosInstancia(slug, {
    busca,
    fornecedor,
    status,
    page: pagina,
    pageSize: TAMANHO_PAGINA,
  })

  const total = data?.count ?? 0
  const totalPaginas = data ? Math.max(1, Math.ceil(data.count / TAMANHO_PAGINA)) : 1
  const temFiltros = Boolean(busca || fornecedor || status)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-header-section text-foreground">Produtos no espelho local</h2>
        <p className="text-caption-label text-muted-foreground">
          Variações (SKUs) sincronizadas dos fornecedores para esta instância. Somente leitura —
          {" "}
          {isLoading ? "carregando…" : `${formatarNumero(total)} ${total === 1 ? "variação encontrada" : "variações encontradas"}`}
          .
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[240px] max-w-sm flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={buscaInput}
            onChange={(event) => setBuscaInput(event.target.value)}
            placeholder="Buscar por SKU, código ou descrição"
            className="pl-8"
          />
        </div>

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
          onValueChange={(valor) => setStatus(valor === "todos" ? "" : (valor as StatusVariacao))}
        >
          <SelectTrigger>
            <SelectValue placeholder="Situação" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Situação: Todas</SelectItem>
            {(Object.keys(ROTULO_STATUS_VARIACAO) as StatusVariacao[]).map((valor) => (
              <SelectItem key={valor} value={valor}>
                {ROTULO_STATUS_VARIACAO[valor]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <ProdutosTabela
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
          rotuloItens="variações"
        />
      )}

      {isFetching && !isLoading && (
        <p className="text-center text-caption-label text-muted-foreground">Atualizando…</p>
      )}
    </div>
  )
}
