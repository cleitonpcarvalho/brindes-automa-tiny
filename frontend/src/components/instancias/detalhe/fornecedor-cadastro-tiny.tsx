"use client"

import { useEffect, useState } from "react"
import { AlertTriangle, CloudUpload, Pause, Play } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api/client"
import {
  useCadastrarProdutosTiny,
  useCadastroTinyPreview,
  usePausarCadastroTiny,
  useRetomarCadastroTiny,
} from "@/lib/api/hooks"
import { formatarNumero } from "@/lib/format"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import {
  ROTULO_ESTADO_CADASTRO_TINY,
  VARIANTE_ESTADO_CADASTRO_TINY,
  rotuloRestantes,
} from "./cadastro-tiny-estado"
import type { CadastroTinyEstado, FornecedorEnum } from "@/lib/api/types"

interface Props {
  slug: string
  fornecedor: FornecedorEnum
  estado: CadastroTinyEstado
}

/**
 * "Sincronizar com Tiny" por fornecedor, com Pausar/Retomar. Cada fornecedor
 * tem sua execução independente: XBZ pode estar sincronizando enquanto Asia
 * também sincroniza e Só Marcas está pausado. O backend só agenda — o
 * processamento roda em background; a retomada continua o trabalho pendente
 * sem duplicar (idempotência do fluxo). A UI só oferece a ação possível
 * para o estado atual.
 */
export function FornecedorCadastroTiny({ slug, fornecedor, estado }: Props) {
  const pausar = usePausarCadastroTiny(slug, fornecedor)
  const retomar = useRetomarCadastroTiny(slug, fornecedor)

  const acaoErro =
    (pausar.isError && ((pausar.error as ApiError)?.message ?? "Não foi possível pausar.")) ||
    (retomar.isError && ((retomar.error as ApiError)?.message ?? "Não foi possível retomar.")) ||
    null

  const emAcao = pausar.isPending || retomar.isPending

  return (
    <div className="rounded-lg border border-border bg-secondary/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <h3 className="text-caption-medium font-semibold text-foreground">Cadastro no Tiny</h3>
            {estado.estado !== "pronto" && (
              <Badge variant={VARIANTE_ESTADO_CADASTRO_TINY[estado.estado]}>
                {ROTULO_ESTADO_CADASTRO_TINY[estado.estado]}
              </Badge>
            )}
          </div>
          <p className="max-w-[36rem] text-caption-label text-muted-foreground">
            Cria no Tiny os produtos elegíveis deste fornecedor (uma variação = um produto) e
            sincroniza as imagens. Roda em segundo plano — pode pausar e retomar.
          </p>
          {estado.execucao_id != null && <Progresso estado={estado} />}
          {estado.estado === "interrompido" && (
            <p className="text-caption-label text-warning">
              A sincronização foi interrompida (o processamento parou sem terminar). Retome para
              continuar de onde parou.
            </p>
          )}
          {estado.estado === "parcial" && estado.mensagem_erro && (
            <p className="text-caption-label text-error">{estado.mensagem_erro}</p>
          )}
          {acaoErro && <p className="text-caption-label text-error">{acaoErro}</p>}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {estado.pode_pausar && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => pausar.mutate()}
              disabled={emAcao}
            >
              <Pause size={14} />
              Pausar
            </Button>
          )}
          {estado.pode_retomar && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => retomar.mutate()}
              disabled={emAcao}
            >
              <Play size={14} className={retomar.isPending ? "animate-spin" : undefined} />
              {retomar.isPending ? "Retomando…" : "Retomar"}
            </Button>
          )}
          {estado.estado === "pausando" && (
            <span className="text-caption-label text-muted-foreground">
              Terminando o produto atual…
            </span>
          )}
          {estado.pode_iniciar && (
            <IniciarCadastroDialog
              slug={slug}
              fornecedor={fornecedor}
              jaConcluiuAntes={estado.estado === "concluido" || estado.estado === "parcial"}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function Progresso({ estado }: { estado: CadastroTinyEstado }) {
  const pct = Math.round((estado.progresso ?? 0) * 100)
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-caption-label text-muted-foreground">
        <span>
          <strong className="text-foreground">{formatarNumero(estado.total_cadastrados)}</strong> cadastrados
        </span>
        <span>
          <strong className="text-foreground">{formatarNumero(estado.total_erros)}</strong> erros
        </span>
        <span>
          <strong className="text-foreground">{formatarNumero(estado.total_ignorados)}</strong>{" "}
          {rotuloRestantes(estado.estado)}
        </span>
      </div>
      <div className="h-1.5 w-56 max-w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-[width]"
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  )
}

function IniciarCadastroDialog({
  slug,
  fornecedor,
  jaConcluiuAntes,
}: {
  slug: string
  fornecedor: FornecedorEnum
  jaConcluiuAntes: boolean
}) {
  const [aberto, setAberto] = useState(false)
  const [iniciada, setIniciada] = useState(false)
  const preview = useCadastroTinyPreview(slug, fornecedor, { enabled: aberto })
  const cadastrar = useCadastrarProdutosTiny(slug, fornecedor)

  useEffect(() => {
    if (!aberto) setIniciada(false)
  }, [aberto])

  const emAndamento = preview.data?.sincronizacao_em_andamento === true
  const podeConfirmar =
    preview.data?.pronta_para_cadastro === true &&
    !emAndamento &&
    !preview.isLoading &&
    !cadastrar.isPending

  const erro = cadastrar.isError
    ? (cadastrar.error as ApiError | undefined)?.message ?? "Não foi possível iniciar a sincronização."
    : preview.isError
      ? "Não foi possível estimar os produtos elegíveis."
      : null

  async function confirmar() {
    await cadastrar.mutateAsync()
    setIniciada(true)
  }

  return (
    <Dialog open={aberto} onOpenChange={setAberto}>
      <DialogTrigger asChild>
        <Button variant="secondary" size="sm">
          <CloudUpload size={14} />
          {jaConcluiuAntes ? "Sincronizar de novo" : "Sincronizar com Tiny"}
        </Button>
      </DialogTrigger>

      <DialogContent className="max-w-[34rem]">
        <DialogHeader>
          <DialogTitle>Sincronizar {ROTULO_FORNECEDOR[fornecedor]} com o Tiny</DialogTitle>
          <DialogDescription>
            Confira antes de confirmar — esta ação cria produtos no Tiny.
          </DialogDescription>
        </DialogHeader>

        {iniciada ? (
          <p className="rounded-md border border-success/20 bg-success-subtle px-3 py-2 text-body-default text-success">
            Sincronização iniciada. Ela roda em segundo plano; acompanhe o progresso aqui e na aba
            Execuções — e pode pausar quando quiser.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-body-default sm:grid-cols-2">
              <Linha rotulo="Fornecedor" valor={ROTULO_FORNECEDOR[fornecedor]} />
              <Linha
                rotulo="Produtos elegíveis (estimativa)"
                valor={preview.isLoading ? "…" : formatarNumero(preview.data?.elegiveis ?? 0)}
              />
              {!!preview.data?.ja_cadastradas && (
                <Linha rotulo="Já no Tiny" valor={formatarNumero(preview.data.ja_cadastradas)} />
              )}
              {!!preview.data?.bloqueadas_local && (
                <Linha
                  rotulo="Bloqueados (estoque/regra)"
                  valor={formatarNumero(preview.data.bloqueadas_local)}
                />
              )}
            </dl>

            <div className="flex items-start gap-2 rounded-md border border-warning/20 bg-warning-subtle px-3 py-2 text-caption-medium text-warning">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>
                A operação vai <strong>criar produtos no Tiny</strong> para os SKUs elegíveis e
                enviar as imagens. Produtos já cadastrados e SKUs que já existem no Tiny sem vínculo
                confirmado não são tocados.
              </span>
            </div>

            {preview.data && !preview.data.pronta_para_cadastro && (
              <p className="text-caption-label text-error">{preview.data.motivo_nao_pronta}</p>
            )}
            {emAndamento && preview.data?.pronta_para_cadastro && (
              <p className="text-caption-label text-muted-foreground">
                Já existe uma sincronização aberta para este fornecedor.
              </p>
            )}
            {erro && <p className="text-caption-label text-error">{erro}</p>}
          </div>
        )}

        <DialogFooter>
          {iniciada ? (
            <Button variant="primary" onClick={() => setAberto(false)}>
              Fechar
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => setAberto(false)} disabled={cadastrar.isPending}>
                Cancelar
              </Button>
              <Button variant="primary" onClick={confirmar} disabled={!podeConfirmar}>
                {cadastrar.isPending ? "Iniciando…" : "Confirmar e iniciar"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{rotulo}</dt>
      <dd className="font-semibold text-foreground">{valor}</dd>
    </div>
  )
}
