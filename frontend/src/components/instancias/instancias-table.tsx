"use client"

import { useRouter } from "next/navigation"
import { cn } from "cn"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { FornecedorPills } from "./fornecedor-pills"
import { AcoesMenu } from "./acoes-menu"
import { StatusBadge } from "./status-badge"
import { formatarExpiracaoToken, formatarNumero, formatarTempoRelativo } from "@/lib/format"
import type { InstanciaListagem } from "@/lib/api/types"

const FORNECEDOR_ABREVIADO: Record<string, string> = {
  xbz: "XBZ",
  asia: "ASIA",
  somarcas: "SOMAR",
  spot: "SPOT",
}

const COR_TOKEN: Record<string, string> = {
  expirado: "text-error",
  urgente: "text-warning",
  ok: "text-foreground",
  pendente: "text-muted-foreground",
}

const COLUNAS = 8

interface Props {
  itens: InstanciaListagem[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
}

export function InstanciasTable({ itens, isLoading, isError, onRetry }: Props) {
  const router = useRouter()

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Cliente</TableHead>
            <TableHead>ERP</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Fornecedores</TableHead>
            <TableHead className="text-right">Produtos</TableHead>
            <TableHead>Última sincronização</TableHead>
            <TableHead>Token</TableHead>
            <TableHead className="w-10" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading &&
            Array.from({ length: 6 }).map((_, indice) => (
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
                  <p className="text-body-default text-error">Não foi possível carregar as instâncias.</p>
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
                  <p className="text-body-default text-foreground">Nenhuma instância encontrada</p>
                  <p className="text-caption-label text-muted-foreground">Ajuste a busca ou o filtro de status.</p>
                </div>
              </TableCell>
            </TableRow>
          )}

          {!isLoading &&
            !isError &&
            itens.map((instancia) => {
              const token = formatarExpiracaoToken(instancia.token_expira_em)
              return (
                <TableRow
                  key={instancia.slug}
                  className="group cursor-pointer"
                  onClick={() => router.push(`/instancias/${instancia.slug}`)}
                >
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="text-body-medium text-foreground group-hover:text-primary">
                        {instancia.nome}
                      </span>
                      <span className="text-caption-label text-muted-foreground">{instancia.cnpj || "—"}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="rounded-sm border border-border bg-muted px-1.5 py-px text-code-inline text-muted-foreground">
                      Tiny
                    </span>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={instancia.status} />
                  </TableCell>
                  <TableCell>
                    <FornecedorPills fornecedores={instancia.fornecedores} />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex flex-col items-end">
                      <span className="text-mono-metric text-foreground">
                        {formatarNumero(instancia.produtos.total)}
                      </span>
                      <span className="text-caption-label text-muted-foreground">
                        {formatarNumero(instancia.produtos.cadastrados)} cadastrados
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="text-body-default text-foreground">
                        {formatarTempoRelativo(instancia.ultima_sincronizacao.em)}
                      </span>
                      <span className="text-caption-label text-muted-foreground">
                        {instancia.ultima_sincronizacao.fornecedor
                          ? `Tiny via ${FORNECEDOR_ABREVIADO[instancia.ultima_sincronizacao.fornecedor]}`
                          : "Sem execuções"}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className={cn(COR_TOKEN[token.estado])}>{token.texto}</span>
                  </TableCell>
                  <TableCell onClick={(event) => event.stopPropagation()}>
                    <AcoesMenu slug={instancia.slug} />
                  </TableCell>
                </TableRow>
              )
            })}
        </TableBody>
      </Table>
    </div>
  )
}
