"use client"

import { useEffect, useState, type ReactNode } from "react"
import Link from "next/link"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, CircleAlert, RefreshCw, Send } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ui/empty-error-state"
import { ApiError } from "@/lib/api/client"
import {
  useAtualizarVariacaoFornecedor,
  useAtualizarVariacaoTiny,
  useStatusAtualizarVariacaoFornecedor,
  useVariacaoInstancia,
} from "@/lib/api/hooks"
import { useToast } from "@/components/ui/toast"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { varianteBadgeStatus } from "./variacao-status"
import { apresentarAtributo, humanizarChave } from "./atributo-formato"
import { VariacaoGaleria } from "./variacao-galeria"
import type { VariacaoDetalhe } from "@/lib/api/types"

const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })
const numero = new Intl.NumberFormat("pt-BR")
const dataHora = new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" })

const TRACO = "—"

function listaDeTextos(valor: unknown): string[] {
  if (!Array.isArray(valor)) return []
  return valor.filter((item): item is string => typeof item === "string" && item.trim() !== "")
}

function registro(valor: unknown): Record<string, unknown> {
  return valor && typeof valor === "object" && !Array.isArray(valor)
    ? (valor as Record<string, unknown>)
    : {}
}

function texto(valor: string | null | undefined): ReactNode {
  return valor && valor.trim() !== "" ? valor : TRACO
}

function moedaTexto(valor: string | null | undefined): ReactNode {
  if (valor == null || valor === "") return TRACO
  const n = Number(valor)
  return Number.isFinite(n) ? moeda.format(n) : valor
}

function dataTexto(iso: string | null | undefined): ReactNode {
  if (!iso) return TRACO
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? TRACO : dataHora.format(d)
}

function medida(valor: number | null | undefined, unidade: string): string | null {
  return typeof valor === "number" ? `${numero.format(valor)} ${unidade}` : null
}

function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-caption-label text-muted-foreground">{rotulo}</dt>
      <dd className="text-body-default break-words text-foreground">{children ?? TRACO}</dd>
    </div>
  )
}

function ListaDeCampos({ children }: { children: ReactNode }) {
  return <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">{children}</dl>
}

function variacaoTexto(dados: VariacaoDetalhe): string {
  return [dados.cor, dados.tamanho, dados.capacidade].filter(Boolean).join(" · ") || TRACO
}

function AcoesVariacao({ dados, slug }: { dados: VariacaoDetalhe; slug: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const fornecedor = useAtualizarVariacaoFornecedor(slug)
  const tiny = useAtualizarVariacaoTiny(slug)
  const [operacaoId, setOperacaoId] = useState<number | null>(null)
  const operacao = useStatusAtualizarVariacaoFornecedor(slug, dados.id, operacaoId)
  const fornecedorEmAtualizacao = fornecedor.isPending || operacao.data?.status === "rodando"
  const emAtualizacao = fornecedorEmAtualizacao || tiny.isPending

  useEffect(() => {
    const dadosOperacao = operacao.data
    const status = dadosOperacao?.status
    if (!operacaoId || !status || status === "rodando") return
    if (status === "sucesso") {
      toast.sucesso("Variação atualizada a partir do fornecedor.")
      queryClient.invalidateQueries({
        queryKey: ["instancias", "produtos", "detalhe", slug, String(dados.id)],
      })
      queryClient.invalidateQueries({ queryKey: ["instancias", "produtos", slug] })
    } else {
      toast.erro(dadosOperacao.erro || "Não foi possível atualizar do fornecedor.")
    }
    setOperacaoId(null)
  }, [dados.id, operacao.data, operacaoId, queryClient, slug, toast])

  const atualizarFornecedor = () => {
    if (emAtualizacao) return
    fornecedor.mutate(dados.id, {
      onSuccess: (resultado) => setOperacaoId(resultado.id),
      onError: (erro) =>
        toast.erro(erro instanceof ApiError ? erro.message : "Não foi possível atualizar do fornecedor."),
    })
  }

  const atualizarTiny = () => {
    if (emAtualizacao) return
    tiny.mutate(dados.id, {
      onSuccess: () => toast.sucesso("Variação atualizada no Tiny."),
      onError: (erro) =>
        toast.erro(erro instanceof ApiError ? erro.message : "Não foi possível atualizar no Tiny."),
    })
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="secondary"
        size="sm"
        disabled={emAtualizacao}
        onClick={atualizarFornecedor}
      >
        <RefreshCw size={14} className={fornecedorEmAtualizacao ? "animate-spin" : undefined} />
        {fornecedorEmAtualizacao ? "Atualizando…" : "Atualizar do fornecedor"}
      </Button>
      <Button
        variant="primary"
        size="sm"
        disabled={emAtualizacao}
        onClick={atualizarTiny}
      >
        <Send size={14} className={tiny.isPending ? "animate-spin" : undefined} />
        {tiny.isPending ? "Atualizando…" : "Atualizar no Tiny"}
      </Button>
    </div>
  )
}

function EspecificacoesCard({ dados }: { dados: VariacaoDetalhe }) {
  const dimensoes = [
    medida(dados.largura, "cm") && `Largura ${medida(dados.largura, "cm")}`,
    medida(dados.altura, "cm") && `Altura ${medida(dados.altura, "cm")}`,
    medida(dados.comprimento, "cm") && `Comprimento ${medida(dados.comprimento, "cm")}`,
    medida(dados.diametro, "cm") && `Diâmetro ${medida(dados.diametro, "cm")}`,
  ].filter(Boolean) as string[]

  const pesos = [
    medida(dados.peso_liquido, "kg") && `Líquido ${medida(dados.peso_liquido, "kg")}`,
    medida(dados.peso_bruto, "kg") && `Bruto ${medida(dados.peso_bruto, "kg")}`,
  ].filter(Boolean) as string[]

  const categorias = listaDeTextos(dados.produto_categorias)

  // Todos os atributos existentes (variação + produto, sem duplicar chave),
  // cada valor passado por `apresentarAtributo` — nunca JSON cru nem
  // "[object Object]". Nenhum atributo é descartado: valor vazio vira "—".
  const atributos = new Map<string, string>()
  for (const fonte of [registro(dados.atributos), registro(dados.produto_atributos)]) {
    for (const [chave, valor] of Object.entries(fonte)) {
      if (atributos.has(chave)) continue
      atributos.set(chave, apresentarAtributo(valor))
    }
  }

  const temAlgo =
    dimensoes.length > 0 || pesos.length > 0 || categorias.length > 0 || atributos.size > 0

  if (!temAlgo) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Especificações</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ListaDeCampos>
          {dimensoes.length > 0 && (
            <Campo rotulo="Dimensões">
              <ul className="flex flex-col gap-0.5">
                {dimensoes.map((linha) => (
                  <li key={linha}>{linha}</li>
                ))}
              </ul>
            </Campo>
          )}
          {pesos.length > 0 && (
            <Campo rotulo="Peso">
              <ul className="flex flex-col gap-0.5">
                {pesos.map((linha) => (
                  <li key={linha}>{linha}</li>
                ))}
              </ul>
            </Campo>
          )}
          {categorias.length > 0 && (
            <Campo rotulo="Categorias">
              <div className="flex flex-wrap gap-1.5">
                {categorias.map((categoria) => (
                  <span
                    key={categoria}
                    className="rounded bg-muted px-1.5 py-0.5 text-caption-label text-muted-foreground"
                  >
                    {categoria}
                  </span>
                ))}
              </div>
            </Campo>
          )}
        </ListaDeCampos>

        {atributos.size > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-caption-label text-muted-foreground">Atributos do fornecedor</p>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
              {[...atributos.entries()].map(([chave, valor]) => (
                <div key={chave} className="flex justify-between gap-3 border-b border-border-subtle py-1">
                  <dt className="text-body-default text-muted-foreground">{humanizarChave(chave)}</dt>
                  <dd className="min-w-0 text-body-default break-words text-right text-foreground">{valor}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function DadosTecnicos({ dados }: { dados: VariacaoDetalhe }) {
  const linhas: Array<[string, ReactNode]> = [
    ["ID da variação", dados.id],
    ["ID do produto-pai", dados.produto_id],
    ["Criado no espelho", dataTexto(dados.criado_em)],
    ["Atualizado no espelho", dataTexto(dados.atualizado_em)],
    ["Atualizado no fornecedor", dataTexto(dados.produto_atualizado_em_fornecedor)],
    ["Cadastrado no Tiny em", dataTexto(dados.cadastrado_em)],
    [
      "Estoque sincronizado no Tiny",
      dados.estoque_tiny_sincronizado == null ? TRACO : numero.format(dados.estoque_tiny_sincronizado),
    ],
    ["Custo sincronizado no Tiny", moedaTexto(dados.preco_custo_tiny_sincronizado)],
    ["Dados corrigidos no Tiny em", dataTexto(dados.dados_tiny_sincronizados_em)],
    ["Imagens confirmadas no Tiny", listaDeTextos(dados.imagens_tiny_sincronizadas).length],
    ["Hash do conteúdo", dados.hash_conteudo ? <code className="text-code-inline">{dados.hash_conteudo}</code> : TRACO],
  ]

  return (
    <details className="group rounded-xl border border-border bg-card">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-header-section text-foreground">
        Dados técnicos
        <span className="text-caption-label text-muted-foreground group-open:hidden">mostrar</span>
        <span className="hidden text-caption-label text-muted-foreground group-open:inline">ocultar</span>
      </summary>
      <div className="border-t border-border px-4 py-3">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
          {linhas.map(([rotulo, valor]) => (
            <div key={rotulo} className="flex justify-between gap-3 border-b border-border-subtle py-1">
              <dt className="text-body-default text-muted-foreground">{rotulo}</dt>
              <dd className="text-body-default break-all text-right text-foreground">{valor}</dd>
            </div>
          ))}
        </dl>
      </div>
    </details>
  )
}

function Conteudo({ slug, dados }: { slug: string; dados: VariacaoDetalhe }) {
  const galeria = listaDeTextos(dados.imagens)
  const imagens = galeria.length > 0 ? galeria : listaDeTextos(dados.produto_imagens)
  const mostrarNomeVariacao = Boolean(dados.nome) && dados.nome !== dados.produto_nome

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 border-b border-border pb-4">
        <Link
          href={`/instancias/${slug}?tab=produtos`}
          className="flex w-fit items-center gap-1.5 text-caption-label text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft size={14} />
          Voltar para Produtos
        </Link>

        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-title-page text-foreground">{dados.produto_nome || dados.nome || dados.sku}</h1>
          <span className="text-caption-label text-muted-foreground">Código fornecedor:</span>
          <span className="rounded bg-muted px-2 py-0.5 font-mono text-code-inline text-muted-foreground">
            {dados.codigo_fornecedor || dados.sku}
          </span>
          <span className="text-caption-label text-muted-foreground">SKU Tiny:</span>
          <span className="rounded bg-muted px-2 py-0.5 font-mono text-code-inline text-foreground">
            {dados.sku_tiny || TRACO}
          </span>
          <Badge variant="neutral">{ROTULO_FORNECEDOR[dados.fornecedor]}</Badge>
          <Badge variant={varianteBadgeStatus(dados.status)}>{dados.status_rotulo}</Badge>
          {dados.produto_descontinuado && <Badge variant="neutral">Descontinuado</Badge>}
        </div>

        {(mostrarNomeVariacao || dados.produto_descricao) && (
          // Teto de largura de leitura via valor ARBITRÁRIO (`max-w-[42rem]`),
          // não os utilitários `max-w-sm/lg/2xl/…`: neste projeto o
          // `@theme` de globals.css define tokens `--spacing-sm/2xl/…`, e o
          // Tailwind v4 resolve `max-w-<nome>` por esse namespace — então
          // `max-w-2xl` compila para `max-width:24px` e o bloco colapsa,
          // quebrando o texto letra por letra. O valor arbitrário é emitido
          // literal e não passa por essa resolução.
          <div className="max-w-[42rem]">
            {mostrarNomeVariacao && (
              <p className="text-body-default text-muted-foreground">{dados.nome}</p>
            )}
            {dados.produto_descricao && (
              <p className="mt-1 text-body-default leading-relaxed break-words text-muted-foreground">
                {dados.produto_descricao}
              </p>
            )}
          </div>
        )}
        <AcoesVariacao dados={dados} slug={slug} />
      </div>

      {dados.ultimo_erro && (
        <div className="flex items-start gap-2 rounded-lg border border-error/20 bg-error-subtle px-4 py-3 text-body-default text-error">
          <CircleAlert size={16} className="mt-0.5 shrink-0" />
          <span className="break-words">{dados.ultimo_erro}</span>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
        <div>
          <VariacaoGaleria imagens={imagens} alt={dados.produto_nome || dados.sku} />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Informações principais</CardTitle>
          </CardHeader>
          <CardContent>
            <ListaDeCampos>
              <Campo rotulo="Fornecedor">{dados.fornecedor_rotulo || ROTULO_FORNECEDOR[dados.fornecedor]}</Campo>
              <Campo rotulo="Código fornecedor">
                <span className="font-mono text-[13px]">{dados.codigo_fornecedor || dados.sku}</span>
              </Campo>
              <Campo rotulo="SKU Tiny">
                <span className="font-mono text-[13px]">{texto(dados.sku_tiny)}</span>
              </Campo>
              <Campo rotulo="Código / referência do produto">
                <span className="font-mono text-[13px]">{texto(dados.produto_codigo_pai)}</span>
              </Campo>
              <Campo rotulo="Produto">{texto(dados.produto_nome)}</Campo>
              <Campo rotulo="Variação / cor">{variacaoTexto(dados)}</Campo>
              <Campo rotulo="Estoque no fornecedor">
                <span className={(dados.estoque ?? 0) <= 0 ? "text-warning" : undefined}>
                  {numero.format(dados.estoque ?? 0)}
                </span>
              </Campo>
              <Campo rotulo="Preço do fornecedor">{moedaTexto(dados.preco)}</Campo>
              <Campo rotulo="NCM">
                <span className="font-mono text-[13px]">{texto(dados.ncm)}</span>
              </Campo>
              <Campo rotulo="Situação no Tiny">
                <Badge variant={varianteBadgeStatus(dados.status)}>{dados.status_rotulo}</Badge>
              </Campo>
              {dados.tiny_id && (
                <Campo rotulo="Tiny ID">
                  <span className="font-mono text-[13px]">{dados.tiny_id}</span>
                </Campo>
              )}
            </ListaDeCampos>
          </CardContent>
        </Card>
      </div>

      <EspecificacoesCard dados={dados} />
      <DadosTecnicos dados={dados} />
    </div>
  )
}

export function VariacaoDetalheView({
  slug,
  variacaoId,
}: {
  slug: string
  variacaoId: string
}) {
  const { data, isLoading, isError, error, refetch } = useVariacaoInstancia(slug, variacaoId)

  const voltar = (
    <Link
      href={`/instancias/${slug}?tab=produtos`}
      className="flex w-fit items-center gap-1.5 text-caption-label text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft size={14} />
      Voltar para Produtos
    </Link>
  )

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        {voltar}
        <Skeleton className="h-9 w-80" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
          <Skeleton className="aspect-square w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      </div>
    )
  }

  if (isError || !data) {
    const naoEncontrada = error instanceof ApiError && error.status === 404
    return (
      <div className="flex flex-col gap-6">
        {voltar}
        {naoEncontrada ? (
          <div className="flex flex-col items-center gap-1 rounded-xl border border-border bg-card px-4 py-12 text-center">
            <p className="text-body-default text-foreground">Variação não encontrada</p>
            <p className="text-caption-label text-muted-foreground">
              Ela pode ter sido removida do espelho ou pertence a outra instância.
            </p>
          </div>
        ) : (
          <ErrorState onRetry={() => refetch()} />
        )}
      </div>
    )
  }

  return <Conteudo slug={slug} dados={data} />
}
