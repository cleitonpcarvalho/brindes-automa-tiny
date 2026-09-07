"use client"

import { useState } from "react"
import { AlertTriangle, ChevronDown, ChevronUp, RefreshCw } from "lucide-react"
import { cn } from "cn"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useSincronizarFornecedor } from "@/lib/api/hooks"
import { formatarNumero, formatarTempoRelativo } from "@/lib/format"
import { DOT_POR_COR, ROTULO_FORNECEDOR, ROTULO_POR_COR } from "../cor-fornecedor"
import { badgeStatus, ROTULO_TIPO } from "./execucao-formato"
import { FornecedorCredenciaisForm } from "./fornecedor-credenciais-form"
import { FornecedorCadenciaForm } from "./fornecedor-cadencia-form"
import { FornecedorCotaCallout } from "./fornecedor-cota-callout"
import type { CadenciaFornecedor, CredencialFornecedorResposta, FornecedorDetalhe } from "@/lib/api/types"

const VARIANTE_BADGE_POR_COR = {
  ok: "success",
  atencao: "warning",
  erro: "error",
  nao_configurado: "neutral",
} as const

interface Props {
  statusDetalhe: FornecedorDetalhe
  credencial: CredencialFornecedorResposta
  cadencia: CadenciaFornecedor
  mensagemErroUltimaExecucao?: string
  slug: string
  defaultExpanded?: boolean
}

export function FornecedorAcordeao({
  statusDetalhe,
  credencial,
  cadencia,
  mensagemErroUltimaExecucao,
  slug,
  defaultExpanded = false,
}: Props) {
  const [expandido, setExpandido] = useState(defaultExpanded)
  const sincronizar = useSincronizarFornecedor(slug, statusDetalhe.fornecedor)
  const fornecedor = statusDetalhe.fornecedor
  const rotuloStatus = credencial.configurado && statusDetalhe.cor === "nao_configurado"
    ? "Configurado"
    : ROTULO_POR_COR[statusDetalhe.cor]

  const rodando = statusDetalhe.ultima_execucao_status === "rodando"
  // "Processando…" tanto no POST em voo (isPending) quanto depois que o backend
  // já registrou a Execucao como rodando — o operador vê a mudança na hora.
  const processando = rodando || sincronizar.isPending
  const nuncaImportou = statusDetalhe.produtos_total === 0 && !statusDetalhe.ultima_execucao_em
  const rotuloBotao = processando
    ? "Processando…"
    : nuncaImportou
      ? "Iniciar carga inicial"
      : "Sincronizar"
  const erroSincronizar = sincronizar.isError
    ? (sincronizar.error as Error | undefined)?.message ?? "Não foi possível iniciar a sincronização."
    : null
  // Botão inerte por falta de credencial ativa: explica o porquê em vez de
  // ficar "clicável mas sem efeito".
  const bloqueadoPorCredencial = !statusDetalhe.credencial_ativa && !processando

  const descricao = statusDetalhe.ultima_execucao_em
    ? `${statusDetalhe.ultima_execucao_status === "falha" ? "falha " : ""}${formatarTempoRelativo(statusDetalhe.ultima_execucao_em)} · ${formatarNumero(statusDetalhe.produtos_total)} produtos sincronizados · intervalo ${cadencia.intervalo_minutos ?? 60}min`
    : "ainda sem execuções"

  return (
    <article className="overflow-hidden rounded-xl bg-card">
      <div
        className="flex cursor-pointer items-center justify-between p-4 transition-colors hover:bg-secondary/50"
        onClick={() => setExpandido((atual) => !atual)}
      >
        <div className="flex items-center gap-3">
          <span className="relative flex size-2.5">
            {statusDetalhe.cor === "ok" && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-75" />
            )}
            <span className={cn("relative inline-flex size-2.5 rounded-full", DOT_POR_COR[statusDetalhe.cor])} />
          </span>
          <h2 className="text-body-medium font-semibold text-foreground">{ROTULO_FORNECEDOR[fornecedor]}</h2>
          <Badge variant={VARIANTE_BADGE_POR_COR[statusDetalhe.cor]}>{rotuloStatus}</Badge>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-caption-label text-muted-foreground">{descricao}</span>
          {/*
            Envelope que isola os cliques do botão do onClick do cabeçalho (que
            abre/fecha o acordeão). Precisa ser um elemento com área real: um
            botão DESABILITADO tem `pointer-events: none` e, sem este envelope,
            o clique "atravessava" para o cabeçalho e só alternava o acordeão.
          */}
          <span
            className="inline-flex flex-col items-end gap-1"
            role="presentation"
            onClick={(event) => event.stopPropagation()}
          >
            <Button
              variant="secondary"
              size="sm"
              onClick={() => sincronizar.mutate()}
              disabled={!statusDetalhe.credencial_ativa || processando}
            >
              <RefreshCw
                size={14}
                className={processando ? "animate-spin" : undefined}
              />
              {rotuloBotao}
            </Button>
            {bloqueadoPorCredencial && (
              <span className="text-caption-label text-muted-foreground">
                Ative a credencial deste fornecedor para iniciar.
              </span>
            )}
          </span>
          <button
            type="button"
            aria-label={expandido ? "Recolher detalhes" : "Expandir detalhes"}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            {expandido ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {erroSincronizar && (
        <div
          role="alert"
          className="flex items-center gap-2 border-t border-error/20 bg-error-subtle px-4 py-2.5 text-caption-medium text-error"
        >
          <AlertTriangle size={14} className="shrink-0" />
          <span>{erroSincronizar}</span>
        </div>
      )}

      {!expandido && statusDetalhe.cor === "erro" && mensagemErroUltimaExecucao && (
        <div className="flex items-center gap-2 border-t border-error/20 bg-error-subtle px-4 py-2.5 text-caption-medium text-error">
          <AlertTriangle size={14} className="shrink-0" />
          <span>Falha na última execução · {mensagemErroUltimaExecucao}</span>
        </div>
      )}

      {expandido && (
        <div className="border-t border-border p-6">
          <UltimaCargaResumo detalhe={statusDetalhe} rodando={rodando} />
          <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
            <FornecedorCredenciaisForm fornecedor={fornecedor} credencial={credencial} slug={slug} />
            <FornecedorCadenciaForm fornecedor={fornecedor} cadencia={cadencia} slug={slug} />
          </div>
          {fornecedor === "xbz" && <FornecedorCotaCallout />}
        </div>
      )}
    </article>
  )
}

function UltimaCargaResumo({ detalhe, rodando }: { detalhe: FornecedorDetalhe; rodando: boolean }) {
  const execucao = detalhe.ultima_execucao
  const badge = badgeStatus(detalhe.ultima_execucao_status ?? "")

  return (
    <div className="mb-6 rounded-lg bg-secondary/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-caption-medium font-semibold text-foreground">Última carga</h3>
        {detalhe.ultima_execucao_status ? (
          <>
            <Badge variant={badge.variant}>{badge.rotulo}</Badge>
            {execucao && (
              <span className="text-caption-label text-muted-foreground">
                {ROTULO_TIPO[execucao.tipo] ?? execucao.tipo} · {formatarTempoRelativo(execucao.iniciada_em)}
              </span>
            )}
          </>
        ) : (
          <span className="text-caption-label text-muted-foreground">ainda sem execuções</span>
        )}
      </div>

      {execucao && (
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-caption-label sm:grid-cols-3">
          <ResumoItem rotulo="Lidos" valor={execucao.total_lidos} />
          <ResumoItem rotulo="Novos" valor={execucao.total_novos} />
          <ResumoItem rotulo="Atualizados" valor={execucao.total_atualizados} />
          <ResumoItem rotulo="Ignorados" valor={execucao.total_ignorados} />
          <ResumoItem rotulo="Erros" valor={execucao.total_erros} />
        </dl>
      )}

      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 border-t border-border pt-3 text-caption-label sm:grid-cols-3">
        <ResumoItem rotulo="No espelho" valor={detalhe.produtos_total} />
        <ResumoItem rotulo="Sem estoque (aguardando)" valor={detalhe.produtos_aguardando} />
        <ResumoItem rotulo="Descontinuados (P@)" valor={detalhe.produtos_descontinuados} />
      </dl>

      {rodando && (
        <p className="mt-3 text-caption-label text-muted-foreground">
          Processando em segundo plano — esta tela atualiza sozinha quando terminar.
        </p>
      )}
      {execucao?.status === "falha" && execucao.mensagem_erro && (
        <p className="mt-3 text-caption-label text-error">{execucao.mensagem_erro}</p>
      )}
    </div>
  )
}

function ResumoItem({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{rotulo}</dt>
      <dd className="font-semibold text-foreground">{formatarNumero(valor)}</dd>
    </div>
  )
}
