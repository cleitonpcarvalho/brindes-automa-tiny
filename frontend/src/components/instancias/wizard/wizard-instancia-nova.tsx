"use client"

import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { ArrowLeft } from "lucide-react"
import Link from "next/link"
import { ApiError } from "@/lib/api/client"
import { useAtualizarInstancia, useAutorizar, useCriarInstancia, useInstancia } from "@/lib/api/hooks"
import { StepIndicator } from "./step-indicator"
import { SummaryStrip } from "./summary-strip"
import { Passo1Identificacao, type DadosIdentificacao } from "./passo-1-identificacao"
import { Passo2Credenciais, type DadosCredenciaisTiny } from "./passo-2-credenciais"
import { Passo3Autorizacao } from "./passo-3-autorizacao"

type Passo = 1 | 2 | 3

export function WizardInstanciaNova() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const slugInicial = searchParams.get("slug")
  const autorizacaoFalhou = searchParams.get("erro") === "1"

  const [slug, setSlug] = useState<string | null>(slugInicial)
  const [passo, setPasso] = useState<Passo>(slugInicial ? 3 : 1)
  const [identificacao, setIdentificacao] = useState<DadosIdentificacao>({ nome: "", cnpj: "" })
  const [credenciais, setCredenciais] = useState<DadosCredenciaisTiny>({ client_id: "", client_secret: "" })

  const { data: instancia } = useInstancia(slug ?? "")
  const criarInstancia = useCriarInstancia()
  const atualizarInstancia = useAtualizarInstancia(slug ?? "")
  const autorizar = useAutorizar(slug ?? "")

  // Ao voltar do callback (?slug=...&erro=1) ou ao reabrir a página com uma
  // instância já criada, preenche os passos anteriores com o que já existe.
  useEffect(() => {
    if (!instancia) return
    setIdentificacao({ nome: instancia.nome, cnpj: instancia.cnpj ?? "" })
    setCredenciais((atual) => ({ ...atual, client_id: instancia.client_id ?? "" }))
  }, [instancia])

  const salvandoCredenciais = criarInstancia.isPending || atualizarInstancia.isPending
  const erroCredenciais = criarInstancia.error ?? atualizarInstancia.error
  const mensagemErroCredenciais = erroCredenciais instanceof ApiError ? erroCredenciais.message : null

  async function handleAvancarIdentificacao(dados: DadosIdentificacao) {
    setIdentificacao(dados)
    setPasso(2)
  }

  async function handleAvancarCredenciais(dados: DadosCredenciaisTiny) {
    setCredenciais(dados)
    if (slug) {
      await atualizarInstancia.mutateAsync({
        client_id: dados.client_id,
        ...(dados.client_secret ? { client_secret: dados.client_secret } : {}),
      })
    } else {
      const criada = await criarInstancia.mutateAsync({
        nome: identificacao.nome,
        cnpj: identificacao.cnpj || undefined,
        client_id: dados.client_id,
        client_secret: dados.client_secret,
      })
      setSlug(criada.slug)
      router.replace(`/instancias/novo?slug=${criada.slug}`)
    }
    setPasso(3)
  }

  async function handleAutorizar() {
    const resposta = await autorizar.mutateAsync();
    window.location.href = resposta.url_autorizacao
  }

  return (
    <div className="mx-auto flex w-full max-w-[720px] flex-col gap-1 pt-4 pb-16">
      <Link
        href="/instancias"
        className="mb-4 flex w-fit items-center gap-1.5 text-caption-label text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Voltar para instâncias
      </Link>

      <StepIndicator passoAtual={passo} />

      {passo === 3 && (
        <SummaryStrip nome={identificacao.nome} cnpj={identificacao.cnpj || undefined} onEditar={() => setPasso(1)} />
      )}

      {passo === 1 && <Passo1Identificacao valorInicial={identificacao} onAvancar={handleAvancarIdentificacao} />}

      {passo === 2 && (
        <Passo2Credenciais
          valorInicial={credenciais}
          clientSecretJaConfigurado={Boolean(slug)}
          isSubmitting={salvandoCredenciais}
          erro={mensagemErroCredenciais}
          onVoltar={() => setPasso(1)}
          onAvancar={handleAvancarCredenciais}
        />
      )}

      {passo === 3 && slug && (
        <Passo3Autorizacao
          redirectUri={instancia?.url_callback ?? ""}
          status={instancia?.status ?? "nao_conectado"}
          autorizacaoFalhou={autorizacaoFalhou}
          isAutorizando={autorizar.isPending}
          onVoltar={() => setPasso(2)}
          onAutorizar={handleAutorizar}
        />
      )}
    </div>
  )
}
