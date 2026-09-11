"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, ChevronDown, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ui/empty-error-state"
import { useToast } from "@/components/ui/toast"
import { ApiError } from "@/lib/api/client"
import { invalidarSincronizacaoTiny } from "@/lib/api/invalidacao-tiny"
import {
  useExecucaoDetalhe,
  useExecucaoLogsGerais,
  useExecucaoProdutos,
  useRetentarLote,
  usePararRetentarLote,
  useRetentarLoteProgresso,
} from "@/lib/api/hooks"
import { formatarDataHora, formatarDuracao, formatarNumero, formatarTempoRelativo } from "@/lib/format"
import { PaginationFooter } from "@/components/instancias/pagination-footer"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { badgeStatus } from "./execucao-formato"
import {
  ROTULO_ESTADO_CADASTRO_TINY,
  VARIANTE_ESTADO_CADASTRO_TINY,
} from "./cadastro-tiny-estado"
import { ExecucaoProdutosTabela } from "./execucao-produtos-tabela"
import { RetentarLoteBarra } from "./retentar-lote-barra"
import type { CadastroTinyEstadoEnum, ExecucaoDetalhe } from "@/lib/api/types"

const TAMANHO_PAGINA = 25

const FILTROS = [
  { chave: "" as const, rotulo: "Todos" },
  { chave: "cadastrados" as const, rotulo: "Cadastrados" },
  { chave: "erros" as const, rotulo: "Erros" },
  { chave: "bloqueados" as const, rotulo: "Ignorados / bloqueados" },
]

function EstadoBadge({ estado }: { estado: string }) {
  if (estado in ROTULO_ESTADO_CADASTRO_TINY) {
    const e = estado as CadastroTinyEstadoEnum
    return <Badge variant={VARIANTE_ESTADO_CADASTRO_TINY[e]}>{ROTULO_ESTADO_CADASTRO_TINY[e]}</Badge>
  }
  const b = badgeStatus(estado)
  return <Badge variant={b.variant}>{b.rotulo}</Badge>
}

function Resumo({ resumo }: { resumo: ExecucaoDetalhe }) {
  const cadastroTiny = resumo.tipo === "cadastro_tiny"
  const semantica = resumo.resumo
  const metricas = semantica?.metricas ?? (cadastroTiny
    ? [
        { chave: "total_fila", rotulo: "Produtos com resultado", valor: resumo.total_lidos ?? 0 },
        { chave: "cadastrados", rotulo: "Cadastrados", valor: resumo.total_cadastrados ?? 0 },
        { chave: "erros", rotulo: "Erros", valor: resumo.total_erros ?? 0 },
        { chave: "ignorados", rotulo: "Ignorados / bloqueados", valor: resumo.total_ignorados ?? 0 },
      ]
    : [])
  const progresso = semantica?.progresso ?? resumo.progresso
  const temPercentual = progresso != null
  const pct = temPercentual ? Math.round(progresso * 100) : 0

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-code-inline text-foreground">
            {ROTULO_FORNECEDOR[resumo.fornecedor as keyof typeof ROTULO_FORNECEDOR] ?? resumo.fornecedor}
          </span>
          <span className="text-caption-label text-muted-foreground">Estado da execução:</span>
          <EstadoBadge estado={resumo.estado} />
          <span className="text-caption-label text-muted-foreground">
            Início: {formatarDataHora(resumo.iniciada_em, true)} ({formatarTempoRelativo(resumo.iniciada_em)})
          </span>
          <span className="text-caption-label text-muted-foreground">·</span>
          <span className="text-caption-label text-muted-foreground">
            Término: {formatarDataHora(resumo.finalizada_em, true)} · Duração: {formatarDuracao(resumo.duracao_segundos)}
          </span>
        </div>

        {semantica?.motivo_status && resumo.status !== "sucesso" && (
          <p className="rounded-md bg-error-subtle/40 px-3 py-2 text-body-default text-error">
            {semantica.motivo_status}
          </p>
        )}

        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {metricas.map((metrica) => (
            <Metrica
              key={metrica.chave}
              rotulo={metrica.rotulo}
              valor={metrica.valor}
              destaque={metrica.chave === "cadastrados" ? "success" : metrica.chave === "erros" && metrica.valor ? "error" : undefined}
            />
          ))}
        </dl>

        {temPercentual ? (
          <div className="flex flex-col gap-1">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-[width]"
                style={{ width: `${pct}%` }}
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
            <span className="text-caption-label text-muted-foreground">{semantica?.progresso_rotulo ?? `${pct}% processado`}</span>
          </div>
        ) : (
          <span className="text-caption-label text-muted-foreground">{semantica?.progresso_rotulo ?? "Sem percentual disponível"}</span>
        )}
        {cadastroTiny && <p className="text-caption-label text-muted-foreground">
          Contagens e filtros consideram os produtos desta execução e seu estado conciliado no espelho.
          O histórico de cada tentativa permanece nos logs.
        </p>}
        {cadastroTiny && resumo.contadores_registrados && (
          <details className="text-caption-label text-muted-foreground">
            <summary>Contadores registrados do fornecedor (última consolidação)</summary>
            Fila: {resumo.contadores_registrados.total_lidos}; cadastrados: {resumo.contadores_registrados.total_cadastrados};
            erros: {resumo.contadores_registrados.total_erros}; pendentes: {resumo.contadores_registrados.total_ignorados}.
          </details>
        )}
      </CardContent>
    </Card>
  )
}

function Metrica({
  rotulo,
  valor,
  destaque,
}: {
  rotulo: string
  valor: number
  destaque?: "success" | "error"
}) {
  const cor = destaque === "success" ? "text-success" : destaque === "error" ? "text-error" : "text-foreground"
  return (
    <div className="flex flex-col rounded-lg bg-muted px-3 py-2">
      <span className={`font-mono text-mono-metric ${cor}`}>{formatarNumero(valor)}</span>
      <span className="text-caption-label text-muted-foreground">{rotulo}</span>
    </div>
  )
}

function LogsTecnicos({ slug, execucaoId, total }: { slug: string; execucaoId: string; total: number }) {
  const [aberto, setAberto] = useState(false)
  const { data, isLoading, isError } = useExecucaoLogsGerais(slug, execucaoId, { enabled: aberto })
  const logs = data?.results ?? []

  return (
    <details
      className="group rounded-xl border border-border bg-card"
      onToggle={(e) => setAberto((e.target as HTMLDetailsElement).open)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-header-section text-foreground">
        Logs técnicos ({total})
        <ChevronDown size={16} className="text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-border px-4 py-3">
        {isLoading && <Skeleton className="h-16 w-full" />}
        {isError && <p className="text-caption-label text-error">Não foi possível carregar os logs técnicos.</p>}
        {!isLoading && !isError && (
          <ul className="flex flex-col gap-2">
            {logs.map((log) => {
              const detalhe =
                log.detalhe && typeof log.detalhe === "object" && Object.keys(log.detalhe).length > 0
                  ? JSON.stringify(log.detalhe, null, 2)
                  : null
              return (
                <li key={log.id} className="flex flex-col gap-1 border-b border-border-subtle py-1.5 last:border-b-0">
                  <div className="flex flex-wrap items-baseline gap-x-2 text-caption-label">
                    <span
                      className={`uppercase ${
                        log.nivel === "erro"
                          ? "text-error"
                          : log.nivel === "aviso"
                            ? "text-warning"
                            : "text-muted-foreground"
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
                    <pre className="overflow-x-auto rounded bg-muted p-2 font-mono text-[12px] text-muted-foreground">
                      {detalhe}
                    </pre>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </details>
  )
}

export function ExecucaoDetalheView({ slug, execucaoId, queryInicial = "" }: {
  slug: string; execucaoId: string; queryInicial?: string
}) {
  const parametros = new URLSearchParams(queryInicial)
  const filtroInicial = FILTROS.find((f) => f.chave === parametros.get("resultado"))?.chave || ""
  const [buscaInput, setBuscaInput] = useState(parametros.get("busca") || "")
  const [busca, setBusca] = useState(buscaInput)
  const [resultado, setResultado] = useState<"" | "cadastrados" | "erros" | "bloqueados">(filtroInicial)
  const [pagina, setPagina] = useState(Math.max(1, Number.parseInt(parametros.get("page") || "1") || 1))
  parametros.set("busca", busca)
  parametros.set("resultado", resultado)
  parametros.set("page", String(pagina))

  useEffect(() => {
    const t = setTimeout(() => setBusca(buscaInput), 300)
    return () => clearTimeout(t)
  }, [buscaInput])

  const queryClient = useQueryClient()
  const toast = useToast()

  const resumo = useExecucaoDetalhe(slug, execucaoId)
  const produtos = useExecucaoProdutos(slug, execucaoId, {
    busca,
    resultado,
    page: pagina,
    pageSize: TAMANHO_PAGINA,
  })

  // ---- retentativa em lote (só no filtro "Erros") ----
  const noFiltroErros = resultado === "erros"
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set())
  const [selecaoTodos, setSelecaoTodos] = useState(false)
  useEffect(() => {
    setSelecionados(new Set())
    setSelecaoTodos(false)
  }, [resultado, busca])

  const loteProgresso = useRetentarLoteProgresso(slug, execucaoId, { enabled: noFiltroErros })
  const loteRodando = loteProgresso.data?.status === "rodando"
  const retentarLote = useRetentarLote(slug, execucaoId)
  const pararRetentarLote = usePararRetentarLote(slug, execucaoId)

  const statusLoteAnterior = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    const st = loteProgresso.data?.status
    if (
      statusLoteAnterior.current === "rodando" &&
      (st === "concluido" || st === "interrompido")
    ) {
      const d = loteProgresso.data
      invalidarSincronizacaoTiny(queryClient, slug)
      queryClient.invalidateQueries({
        queryKey: ["instancias", "execucoes", "produtos", slug, String(execucaoId)],
      })
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] })
      if (st === "concluido") {
        toast.sucesso(
          `Retentativa em lote concluída: ${d?.sucessos ?? 0} cadastrado(s), ${d?.erros ?? 0} com erro.`,
        )
      } else {
        toast.sucesso(
          `Retentativa em lote interrompida: ${d?.processados ?? 0} de ${d?.total ?? 0} processado(s).`,
        )
      }
      setSelecionados(new Set())
      setSelecaoTodos(false)
    }
    statusLoteAnterior.current = st
  }, [loteProgresso.data, queryClient, slug, execucaoId, toast])

  const voltar = (
    <Link
      href={`/instancias/${slug}?tab=execucoes`}
      className="flex w-fit items-center gap-1.5 text-caption-label text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft size={14} />
      Voltar para Execuções
    </Link>
  )

  if (resumo.isLoading) {
    return (
      <div className="flex flex-col gap-6">
        {voltar}
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    )
  }

  if (resumo.isError || !resumo.data) {
    const naoEncontrada = resumo.error instanceof ApiError && resumo.error.status === 404
    return (
      <div className="flex flex-col gap-6">
        {voltar}
        {naoEncontrada ? (
          <div className="flex flex-col items-center gap-1 rounded-xl border border-border bg-card px-4 py-12 text-center">
            <p className="text-body-default text-foreground">Execução não encontrada</p>
            <p className="text-caption-label text-muted-foreground">
              Ela pode ter sido removida ou pertence a outra instância.
            </p>
          </div>
        ) : (
          <ErrorState onRetry={() => resumo.refetch()} />
        )}
      </div>
    )
  }

  const total = produtos.data?.count ?? 0
  const totalPaginas = produtos.data ? Math.max(1, Math.ceil(produtos.data.count / TAMANHO_PAGINA)) : 1
  const temFiltros = Boolean(busca || resultado)
  const aud = resumo.data.auditoria
  const possuiLogsIndividuais = resumo.data.resumo
    ? resumo.data.resumo.logs_individuais_total > 0
    : resumo.data.tipo === "cadastro_tiny"

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 border-b border-border pb-4">
        {voltar}
        <h1 className="text-title-page text-foreground">
          Execução #{resumo.data.id} · {ROTULO_FORNECEDOR[resumo.data.fornecedor as keyof typeof ROTULO_FORNECEDOR] ?? resumo.data.fornecedor}
        </h1>
      </div>

      <Resumo resumo={resumo.data} />

      {possuiLogsIndividuais ? <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] max-w-sm flex-1">
            <Search
              size={14}
              className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={buscaInput}
              onChange={(e) => { setBuscaInput(e.target.value); setPagina(1) }}
              placeholder="Buscar por SKU ou nome do produto"
              className="pl-8"
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {FILTROS.map((f) => (
              <Button
                key={f.chave || "todos"}
                variant={resultado === f.chave ? "secondary" : "ghost"}
                size="sm"
                onClick={() => { setResultado(f.chave); setPagina(1) }}
              >
                {f.rotulo}
                {f.chave === "erros" && aud.erros > 0 && (
                  <span className="ml-1 rounded bg-error-subtle px-1 text-error">{aud.erros}</span>
                )}
                {f.chave === "cadastrados" && (
                  <span className="ml-1 text-muted-foreground">{aud.cadastrados_e_vinculados}</span>
                )}
                {f.chave === "bloqueados" && aud.bloqueados > 0 && (
                  <span className="ml-1 text-muted-foreground">{aud.bloqueados}</span>
                )}
              </Button>
            ))}
          </div>
        </div>

        {noFiltroErros && aud.erros > 0 && (
          <RetentarLoteBarra
            qtdErrosTotal={aud.erros}
            qtdSelecionada={selecionados.size}
            selecaoTodos={selecaoTodos}
            progresso={loteProgresso.data}
            disparando={retentarLote.isPending}
            parando={pararRetentarLote.isPending}
            onParar={() =>
              pararRetentarLote.mutate(undefined, {
                onSuccess: () => toast.sucesso("Parada da retentativa solicitada."),
                onError: (erro) =>
                  toast.erro(
                    erro instanceof ApiError
                      ? erro.message
                      : "Não foi possível parar a retentativa em lote.",
                  ),
              })
            }
            onSelecionarTodos={() => {
              setSelecaoTodos(true)
              setSelecionados(new Set())
            }}
            onLimpar={() => {
              setSelecaoTodos(false)
              setSelecionados(new Set())
            }}
            onDisparar={() =>
              retentarLote.mutate(
                selecaoTodos ? { todos: true, busca } : { variacao_ids: [...selecionados] },
                {
                  onSuccess: () => toast.sucesso("Retentativa em lote iniciada."),
                  onError: (erro) =>
                    toast.erro(
                      erro instanceof ApiError
                        ? erro.message
                        : "Não foi possível iniciar a retentativa em lote.",
                    ),
                },
              )
            }
          />
        )}

        <ExecucaoProdutosTabela
          slug={slug}
          execucaoId={execucaoId}
          retornoExecucao={`/instancias/${slug}/execucoes/${execucaoId}?${parametros}`}
          itens={produtos.data?.results ?? []}
          isLoading={produtos.isLoading}
          isError={produtos.isError}
          onRetry={() => produtos.refetch()}
          temFiltros={temFiltros}
          retryBloqueado={loteRodando}
          selecao={
            noFiltroErros
              ? {
                  selecionados,
                  selecaoTodos,
                  onToggle: (id) =>
                    setSelecionados((s) => {
                      const n = new Set(s)
                      if (n.has(id)) n.delete(id)
                      else n.add(id)
                      return n
                    }),
                  onTogglePagina: (ids, marcar) =>
                    setSelecionados((s) => {
                      const n = new Set(s)
                      ids.forEach((id) => (marcar ? n.add(id) : n.delete(id)))
                      return n
                    }),
                }
              : undefined
          }
        />

        {!produtos.isLoading && !produtos.isError && produtos.data && (
          <PaginationFooter
            pagina={pagina}
            totalPaginas={totalPaginas}
            totalItens={total}
            itensNaPagina={produtos.data.results.length}
            onPageChange={setPagina}
            rotuloItens="SKUs"
          />
        )}
      </div> : (
        <p className="rounded-xl border border-border bg-card px-4 py-6 text-center text-caption-label text-muted-foreground">
          {resumo.data.resumo?.mensagem_logs ?? "Esta execução não possui processamento individual por SKU."}
        </p>
      )}

      <LogsTecnicos slug={slug} execucaoId={execucaoId} total={resumo.data.logs_gerais_total} />
    </div>
  )
}
