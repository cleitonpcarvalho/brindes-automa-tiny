"use client"

import { useEffect, useState } from "react"
import { CheckCircle2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ui/empty-error-state"
import { ApiError } from "@/lib/api/client"
import { useAtualizarConfiguracoes, useConfiguracoesInstancia } from "@/lib/api/hooks"

/**
 * `tiny_origem_padrao` é um código inteiro da tabela de origem da mercadoria
 * (NF-e), 0 a 8 — os validators do model. O sistema só conhece o rótulo de
 * dois deles (help_text de Instancia.tiny_origem_padrao); os demais não têm
 * nome aqui, então a edição é um campo numérico com faixa, sem inventar uma
 * lista de opções. Vazio = não definido (null).
 */
const ORIGEM_MIN = 0
const ORIGEM_MAX = 8

function origemValida(bruto: string): boolean {
  if (bruto === "") return true
  const n = Number(bruto)
  return Number.isInteger(n) && n >= ORIGEM_MIN && n <= ORIGEM_MAX
}

export function ConfiguracoesTinyCard({ slug }: { slug: string }) {
  const { data, isLoading, isError, refetch } = useConfiguracoesInstancia(slug)
  const salvar = useAtualizarConfiguracoes(slug)

  const [origem, setOrigem] = useState("")
  const [unidade, setUnidade] = useState("")
  const [hidratado, setHidratado] = useState(false)

  const carregadoOrigem = data?.tiny_origem_padrao == null ? "" : String(data.tiny_origem_padrao)
  const carregadoUnidade = data?.tiny_unidade_medida_padrao ?? ""
  const alterado = hidratado && (origem.trim() !== carregadoOrigem || unidade.trim() !== carregadoUnidade)

  // Só re-hidrata a partir do servidor quando não há edição pendente — assim
  // um refetch (foco na janela etc.) não descarta o que o usuário digitou.
  useEffect(() => {
    if (data && !alterado) {
      setOrigem(data.tiny_origem_padrao == null ? "" : String(data.tiny_origem_padrao))
      setUnidade(data.tiny_unidade_medida_padrao ?? "")
      setHidratado(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  const origemOk = origemValida(origem)
  const mensagemErro = salvar.error instanceof ApiError ? salvar.error.message : salvar.error ? "Não foi possível salvar." : null

  function handleSalvar() {
    if (!alterado || !origemOk || salvar.isPending) return
    salvar.mutate({
      tiny_origem_padrao: origem.trim() === "" ? null : Number(origem),
      tiny_unidade_medida_padrao: unidade.trim(),
    })
  }

  return (
    <section className="flex flex-col gap-4 rounded-xl bg-card p-4">
      <div>
        <h2 className="text-header-section text-foreground">Configurações do Tiny</h2>
        <p className="text-caption-label text-muted-foreground">
          Valores que o Tiny exige e nenhum fornecedor entrega. Precisam estar definidos antes de cadastrar produtos.
        </p>
      </div>

      {isLoading && <Skeleton className="h-32 w-full rounded-lg" />}
      {isError && <ErrorState onRetry={() => refetch()} />}

      {data && (
        <form
          className="flex flex-col gap-4"
          onSubmit={(evento) => {
            evento.preventDefault()
            handleSalvar()
          }}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`${slug}-origem`}>Origem padrão do produto</Label>
              <Input
                id={`${slug}-origem`}
                type="number"
                inputMode="numeric"
                min={ORIGEM_MIN}
                max={ORIGEM_MAX}
                step={1}
                value={origem}
                onChange={(evento) => setOrigem(evento.target.value)}
                placeholder="Não definida"
                aria-invalid={!origemOk}
                className="font-mono"
              />
              <p className="text-caption-label text-muted-foreground">
                Código da tabela de origem da mercadoria (NF-e), de 0 a 8. 0 = nacional, 1 = estrangeira
                (importação direta). Deixe vazio para não definir.
              </p>
              {!origemOk && (
                <p role="alert" className="text-caption-label text-error">
                  Informe um número inteiro de 0 a 8.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`${slug}-unidade`}>Unidade de medida padrão</Label>
              <Input
                id={`${slug}-unidade`}
                value={unidade}
                maxLength={10}
                onChange={(evento) => setUnidade(evento.target.value)}
                placeholder="Ex.: UN, PC, CX"
                className="font-mono"
              />
              <p className="text-caption-label text-muted-foreground">Até 10 caracteres.</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={!alterado || !origemOk || salvar.isPending}
            >
              {salvar.isPending ? "Salvando…" : "Salvar"}
            </Button>
            {salvar.isSuccess && !alterado && (
              <span className="flex items-center gap-1.5 text-caption-label text-success">
                <CheckCircle2 size={14} />
                Configurações salvas.
              </span>
            )}
            {mensagemErro && (
              <span role="alert" className="text-caption-label text-error">
                {mensagemErro}
              </span>
            )}
          </div>
        </form>
      )}
    </section>
  )
}
