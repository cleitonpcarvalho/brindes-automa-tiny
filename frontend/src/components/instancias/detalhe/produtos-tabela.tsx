"use client"

import { useRouter } from "next/navigation"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { formatarNumero } from "@/lib/format"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { varianteBadgeStatus } from "./variacao-status"
import type { VariacaoEspelho } from "@/lib/api/types"

const COLUNAS = 7

const formatadorMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function variacaoTexto(item: VariacaoEspelho) {
  const partes = [item.cor, item.tamanho, item.capacidade].filter(Boolean)
  return partes.length > 0 ? partes.join(" · ") : "—"
}

function precoTexto(preco: string) {
  const numero = Number(preco)
  return Number.isFinite(numero) ? formatadorMoeda.format(numero) : preco
}

interface Props {
  slug: string
  itens: VariacaoEspelho[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  temFiltros: boolean
}

export function ProdutosTabela({ slug, itens, isLoading, isError, onRetry, temFiltros }: Props) {
  const router = useRouter()

  function abrir(id: number) {
    router.push(`/instancias/${slug}/produtos/${id}`)
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Fornecedor</TableHead>
            <TableHead>SKU / Código</TableHead>
            <TableHead>Produto</TableHead>
            <TableHead>Variação</TableHead>
            <TableHead className="text-right">Estoque</TableHead>
            <TableHead className="text-right">Preço fornecedor</TableHead>
            <TableHead>Situação no Tiny</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading &&
            Array.from({ length: 8 }).map((_, indice) => (
              <TableRow key={indice}>
                <TableCell colSpan={COLUNAS}>
                  <Skeleton className="h-5 w-full" />
                </TableCell>
              </TableRow>
            ))}

          {!isLoading && isError && (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={COLUNAS} className="!py-10 whitespace-normal">
                <div className="flex flex-col items-center gap-2 text-center">
                  <p className="text-body-default text-error">
                    Não foi possível carregar os produtos do espelho.
                  </p>
                  <Button variant="secondary" size="sm" onClick={onRetry}>
                    Tentar de novo
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          )}

          {!isLoading && !isError && itens.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={COLUNAS} className="!py-10 whitespace-normal">
                <div className="flex flex-col items-center gap-1 text-center">
                  <p className="text-body-default text-foreground">Nenhum produto no espelho</p>
                  <p className="text-caption-label text-muted-foreground">
                    {temFiltros
                      ? "Ajuste a busca ou os filtros."
                      : "Os produtos aparecem aqui depois da primeira sincronização com os fornecedores."}
                  </p>
                </div>
              </TableCell>
            </TableRow>
          )}

          {!isLoading &&
            !isError &&
            itens.map((item) => (
              <TableRow
                key={item.id}
                role="link"
                tabIndex={0}
                aria-label={`Ver detalhes de ${item.sku}`}
                className="cursor-pointer"
                onClick={() => abrir(item.id)}
                onKeyDown={(evento) => {
                  if (evento.key === "Enter" || evento.key === " ") {
                    evento.preventDefault()
                    abrir(item.id)
                  }
                }}
              >
                <TableCell>
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-code-inline text-foreground">
                    {ROTULO_FORNECEDOR[item.fornecedor]}
                  </span>
                </TableCell>
                <TableCell className="whitespace-normal">
                  <div className="flex flex-col">
                    <span className="font-mono text-[13px] text-foreground">{item.sku}</span>
                    <span className="text-caption-label text-muted-foreground">
                      {item.produto_codigo_pai}
                    </span>
                  </div>
                </TableCell>
                <TableCell className="max-w-[280px] whitespace-normal">
                  <span className="text-body-default text-foreground">{item.produto_nome}</span>
                  {item.nome && item.nome !== item.produto_nome && (
                    <span className="block text-caption-label text-muted-foreground">{item.nome}</span>
                  )}
                </TableCell>
                <TableCell className="whitespace-normal text-body-default text-muted-foreground">
                  {variacaoTexto(item)}
                </TableCell>
                <TableCell className="text-right">
                  <span className={(item.estoque ?? 0) <= 0 ? "text-warning" : "text-foreground"}>
                    {formatarNumero(item.estoque ?? 0)}
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono text-[13px] text-foreground">
                  {precoTexto(item.preco)}
                </TableCell>
                <TableCell>
                  <Badge variant={varianteBadgeStatus(item.status)}>{item.status_rotulo}</Badge>
                </TableCell>
              </TableRow>
            ))}
        </TableBody>
      </Table>
    </div>
  )
}
