import Link from "next/link"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { formatarDuracao, formatarTempoRelativo } from "@/lib/format"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { ROTULO_TIPO, badgeStatus, resultadoTexto } from "./execucao-formato"
import type { Execucao } from "@/lib/api/types"

const COLUNAS = 7

interface Props {
  slug: string
  itens: Execucao[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  temFiltros: boolean
}

export function ExecucoesHistoricoTabela({ slug, itens, isLoading, isError, onRetry, temFiltros }: Props) {
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Fornecedor</TableHead>
            <TableHead>Tipo</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Início</TableHead>
            <TableHead className="text-right">Duração</TableHead>
            <TableHead>Resultado</TableHead>
            <TableHead className="w-24 text-right">Logs</TableHead>
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
                    Não foi possível carregar o histórico de execuções.
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
                  <p className="text-body-default text-foreground">Nenhuma execução</p>
                  <p className="text-caption-label text-muted-foreground">
                    {temFiltros
                      ? "Ajuste os filtros."
                      : "O histórico aparece aqui a cada sincronização desta instância."}
                  </p>
                </div>
              </TableCell>
            </TableRow>
          )}

          {!isLoading &&
            !isError &&
            itens.map((execucao) => {
              const badge = badgeStatus(execucao.status ?? "")
              return (
                <TableRow
                  key={execucao.id}
                  className={`text-body-default ${execucao.status === "falha" ? "bg-error-subtle/40" : ""}`}
                >
                  <TableCell>
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-code-inline text-foreground">
                      {ROTULO_FORNECEDOR[execucao.fornecedor]}
                    </span>
                  </TableCell>
                  <TableCell className="text-caption-label text-muted-foreground">
                    {ROTULO_TIPO[execucao.tipo] ?? execucao.tipo}
                  </TableCell>
                  <TableCell>
                    <Badge variant={badge.variant}>{badge.rotulo}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-[13px] text-foreground">
                    {formatarTempoRelativo(execucao.iniciada_em)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[13px] text-muted-foreground">
                    {formatarDuracao(execucao.duracao_segundos)}
                  </TableCell>
                  <TableCell
                    className={`max-w-[320px] truncate font-mono text-[13px] ${
                      execucao.status === "falha" ? "text-error" : "text-foreground"
                    }`}
                  >
                    {resultadoTexto(execucao)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" asChild>
                      <Link href={`/instancias/${slug}/execucoes/${execucao.id}`}>
                        {execucao.total_logs === 0 ? "Ver" : `Ver (${execucao.total_logs})`}
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
        </TableBody>
      </Table>
    </div>
  )
}
