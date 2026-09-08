"use client"

import { Fragment, useState } from "react"
import { useRouter } from "next/navigation"
import { ChevronDown, ChevronRight, ImageOff, Images } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useExecucaoProdutoLogs } from "@/lib/api/hooks"
import { formatarTempoRelativo } from "@/lib/format"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ROTULO_RESULTADO, VARIANTE_RESULTADO } from "./execucao-resultado"
import { RetentarBotao } from "./retentar-botao"
import type { ExecucaoProduto } from "@/lib/api/types"

const COLUNAS = 6

interface Props {
  slug: string
  execucaoId: string
  itens: ExecucaoProduto[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  temFiltros: boolean
}

export function ExecucaoProdutosTabela({
  slug,
  execucaoId,
  itens,
  isLoading,
  isError,
  onRetry,
  temFiltros,
}: Props) {
  const router = useRouter()
  const [expandido, setExpandido] = useState<number | null>(null)

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" />
            <TableHead>SKU / Produto</TableHead>
            <TableHead>Resultado</TableHead>
            <TableHead>Tiny ID</TableHead>
            <TableHead>Detalhe / erro</TableHead>
            <TableHead className="w-44 text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading &&
            Array.from({ length: 8 }).map((_, i) => (
              <TableRow key={i}>
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
                    Não foi possível carregar os produtos desta execução.
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
              <TableCell colSpan={COLUNAS} className="!py-10 whitespace-normal text-center">
                <p className="text-body-default text-foreground">
                  {temFiltros ? "Nenhum SKU com esse filtro." : "Esta execução não processou nenhum SKU."}
                </p>
              </TableCell>
            </TableRow>
          )}

          {!isLoading &&
            !isError &&
            itens.map((linha) => {
              const aberto = expandido === linha.log_id
              const irParaProduto = () =>
                linha.variacao_id != null &&
                router.push(`/instancias/${slug}/produtos/${linha.variacao_id}`)
              return (
                <Fragment key={linha.log_id}>
                  <TableRow className={linha.resultado === "erro" ? "bg-error-subtle/30" : ""}>
                    <TableCell className="align-top">
                      <button
                        type="button"
                        aria-label={aberto ? "Recolher" : "Ver mensagem técnica completa"}
                        onClick={() => setExpandido(aberto ? null : linha.log_id)}
                        className="text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      </button>
                    </TableCell>
                    <TableCell className="max-w-[280px] whitespace-normal align-top">
                      <button
                        type="button"
                        onClick={irParaProduto}
                        disabled={linha.variacao_id == null}
                        className="flex flex-col text-left disabled:cursor-default"
                      >
                        <span className="font-mono text-[13px] text-foreground hover:underline">
                          {linha.sku || "—"}
                        </span>
                        <span className="text-caption-label text-muted-foreground">
                          {linha.produto_nome || "(produto removido do espelho)"}
                        </span>
                      </button>
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex items-center gap-1.5">
                        <Badge variant={VARIANTE_RESULTADO[linha.resultado]}>
                          {ROTULO_RESULTADO[linha.resultado]}
                        </Badge>
                        {linha.imagens === "ok" && <Images size={13} className="text-success" />}
                        {linha.imagens === "erro" && <ImageOff size={13} className="text-error" />}
                      </div>
                    </TableCell>
                    <TableCell className="align-top font-mono text-[13px] text-foreground">
                      {linha.tiny_id || "—"}
                    </TableCell>
                    <TableCell className="max-w-[320px] whitespace-normal align-top text-caption-label text-muted-foreground">
                      {linha.detalhe_curto || "—"}
                    </TableCell>
                    <TableCell className="align-top text-right">
                      <div className="flex flex-col items-end gap-1">
                        <RetentarBotao slug={slug} execucaoId={execucaoId} linha={linha} />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={irParaProduto}
                          disabled={linha.variacao_id == null}
                        >
                          Ver produto
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  {aberto && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={COLUNAS} className="whitespace-normal bg-muted/40">
                        <LogsTecnicosDoSku
                          slug={slug}
                          execucaoId={execucaoId}
                          variacaoId={linha.variacao_id}
                        />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              )
            })}
        </TableBody>
      </Table>
    </div>
  )
}

function LogsTecnicosDoSku({
  slug,
  execucaoId,
  variacaoId,
}: {
  slug: string
  execucaoId: string
  variacaoId: number | null
}) {
  const { data, isLoading, isError } = useExecucaoProdutoLogs(slug, execucaoId, variacaoId)
  if (isLoading) return <Skeleton className="h-10 w-full" />
  if (isError) return <p className="text-caption-label text-error">Não foi possível carregar os logs deste SKU.</p>
  const logs = data?.results ?? []
  return (
    <ul className="flex flex-col gap-2 py-1">
      {logs.map((log) => {
        const detalhe =
          log.detalhe && typeof log.detalhe === "object" && Object.keys(log.detalhe).length > 0
            ? JSON.stringify(log.detalhe, null, 2)
            : null
        return (
          <li key={log.id} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-baseline gap-x-2 text-caption-label">
              <span
                className={`uppercase ${
                  log.nivel === "erro" ? "text-error" : log.nivel === "aviso" ? "text-warning" : "text-muted-foreground"
                }`}
              >
                {log.nivel}
              </span>
              <span className="text-body-default text-foreground">{log.mensagem}</span>
              <span className="ml-auto font-mono text-muted-foreground">
                {formatarTempoRelativo(log.criado_em)}
              </span>
            </div>
            {detalhe && (
              <pre className="overflow-x-auto rounded bg-background p-2 font-mono text-[12px] text-muted-foreground">
                {detalhe}
              </pre>
            )}
          </li>
        )
      })}
    </ul>
  )
}
