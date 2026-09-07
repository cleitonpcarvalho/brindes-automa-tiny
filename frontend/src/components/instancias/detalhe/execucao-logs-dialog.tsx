"use client"

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { formatarDuracao, formatarNumero, formatarTempoRelativo } from "@/lib/format"
import { useExecucaoLogs } from "@/lib/api/hooks"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { ROTULO_TIPO, badgeStatus } from "./execucao-formato"
import type { Execucao, LogItem } from "@/lib/api/types"

const NIVEL: Record<string, { rotulo: string; classe: string }> = {
  info: { rotulo: "Info", classe: "text-muted-foreground" },
  aviso: { rotulo: "Aviso", classe: "text-warning" },
  erro: { rotulo: "Erro", classe: "text-error" },
}

const CONTADORES: { chave: keyof Execucao; rotulo: string }[] = [
  { chave: "total_lidos", rotulo: "Lidos" },
  { chave: "total_novos", rotulo: "Novos" },
  { chave: "total_atualizados", rotulo: "Atualizados" },
  { chave: "total_cadastrados", rotulo: "Cadastrados" },
  { chave: "total_ignorados", rotulo: "Ignorados" },
  { chave: "total_erros", rotulo: "Erros" },
]

function LinhaLog({ log }: { log: LogItem }) {
  const nivel = NIVEL[log.nivel ?? "info"] ?? NIVEL.info
  const detalhe =
    log.detalhe && typeof log.detalhe === "object" && Object.keys(log.detalhe).length > 0
      ? JSON.stringify(log.detalhe, null, 2)
      : null

  return (
    <li className="flex flex-col gap-1 border-b border-border-subtle py-2 last:border-b-0">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className={`text-caption-medium uppercase ${nivel.classe}`}>{nivel.rotulo}</span>
        <span className="text-body-default text-foreground">{log.mensagem}</span>
        {log.variacao_sku && (
          <span className="rounded bg-muted px-1 font-mono text-code-inline text-muted-foreground">
            {log.variacao_sku}
          </span>
        )}
        <span className="ml-auto font-mono text-caption-label text-muted-foreground">
          {formatarTempoRelativo(log.criado_em)}
        </span>
      </div>
      {detalhe && (
        <pre className="overflow-x-auto rounded bg-muted p-2 font-mono text-[12px] text-muted-foreground">
          {detalhe}
        </pre>
      )}
    </li>
  )
}

interface Props {
  slug: string
  execucao: Execucao | null
  onOpenChange: (aberto: boolean) => void
}

export function ExecucaoLogsDialog({ slug, execucao, onOpenChange }: Props) {
  const { data, isLoading, isError, refetch } = useExecucaoLogs(slug, execucao?.id ?? null)
  const logs = data?.results ?? []
  const badge = execucao ? badgeStatus(execucao.status ?? "") : null

  return (
    <Dialog open={execucao !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[42rem]">
        {execucao && (
          <div className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>
                Execução · {ROTULO_FORNECEDOR[execucao.fornecedor]}
              </DialogTitle>
              <div className="flex flex-wrap items-center gap-2 text-caption-label text-muted-foreground">
                {badge && <Badge variant={badge.variant}>{badge.rotulo}</Badge>}
                <span>{ROTULO_TIPO[execucao.tipo] ?? execucao.tipo}</span>
                <span>·</span>
                <span>{formatarTempoRelativo(execucao.iniciada_em)}</span>
                <span>·</span>
                <span>{formatarDuracao(execucao.duracao_segundos)}</span>
              </div>
            </DialogHeader>

            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {CONTADORES.map(({ chave, rotulo }) => (
                <div key={chave} className="flex flex-col rounded-lg bg-muted px-2 py-1.5">
                  <span className="font-mono text-body-medium text-foreground">
                    {formatarNumero(Number(execucao[chave] ?? 0))}
                  </span>
                  <span className="text-caption-label text-muted-foreground">{rotulo}</span>
                </div>
              ))}
            </div>

            {execucao.mensagem_erro && (
              <p className="rounded-lg bg-error-subtle/40 px-3 py-2 text-body-default text-error">
                {execucao.mensagem_erro}
              </p>
            )}

            <div className="flex flex-col">
              <span className="mb-1 text-caption-medium text-muted-foreground uppercase tracking-wider">
                Logs
              </span>

              {isLoading && (
                <div className="flex flex-col gap-2 py-2">
                  {Array.from({ length: 4 }).map((_, indice) => (
                    <Skeleton key={indice} className="h-5 w-full" />
                  ))}
                </div>
              )}

              {!isLoading && isError && (
                <div className="flex flex-col items-center gap-2 py-6 text-center">
                  <p className="text-body-default text-error">Não foi possível carregar os logs.</p>
                  <Button variant="secondary" size="sm" onClick={() => refetch()}>
                    Tentar de novo
                  </Button>
                </div>
              )}

              {!isLoading && !isError && logs.length === 0 && (
                <p className="py-6 text-center text-caption-label text-muted-foreground">
                  Esta execução não registrou logs.
                </p>
              )}

              {!isLoading && !isError && logs.length > 0 && (
                <ul className="max-h-[45vh] overflow-y-auto">
                  {logs.map((log) => (
                    <LinhaLog key={log.id} log={log} />
                  ))}
                </ul>
              )}

              {data && data.count > logs.length && (
                <p className="mt-2 text-caption-label text-muted-foreground">
                  Mostrando as primeiras {formatarNumero(logs.length)} de {formatarNumero(data.count)} linhas.
                </p>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
