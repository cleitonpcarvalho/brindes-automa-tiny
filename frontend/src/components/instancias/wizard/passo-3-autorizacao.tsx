"use client"

import { useState } from "react"
import { AlertTriangle, Check, Copy } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import type { StatusInstancia } from "@/lib/api/types"

const ITENS_CHECKLIST = [
  "O aplicativo foi criado na conta do cliente",
  "A URL de retorno acima foi cadastrada no aplicativo",
  "As permissões de produtos e estoque estão habilitadas",
] as const

interface Props {
  redirectUri: string
  status: StatusInstancia
  autorizacaoFalhou: boolean
  isAutorizando: boolean
  onVoltar: () => void
  onAutorizar: () => void
}

const ESTADO_CONEXAO: Record<StatusInstancia, { texto: string; detalhe: string; cor: string }> = {
  nao_conectado: { texto: "Aguardando autorização", detalhe: "Nenhum token ativo para esta instância", cor: "bg-muted-foreground" },
  conectado: { texto: "Conectado", detalhe: "Token ativo — autorização concluída", cor: "bg-success" },
  erro: { texto: "Falha na autorização", detalhe: "Tente autorizar novamente", cor: "bg-error" },
}

/** design/04-instancia-nova — único passo com mockup completo. */
export function Passo3Autorizacao({ redirectUri, status, autorizacaoFalhou, isAutorizando, onVoltar, onAutorizar }: Props) {
  const [copiado, setCopiado] = useState(false)
  const [checklist, setChecklist] = useState<boolean[]>([false, false, false])

  const todosMarcados = checklist.every(Boolean)
  const estado = ESTADO_CONEXAO[status]

  async function copiarRedirectUri() {
    await navigator.clipboard.writeText(redirectUri)
    setCopiado(true)
    setTimeout(() => setCopiado(false), 1500)
  }

  return (
    <div className="rounded-xl border border-border bg-card p-7">
      <header className="mb-6">
        <h1 className="text-title-page-mobile text-foreground">Autorização</h1>
        <p className="mt-1.5 text-body-default text-muted-foreground">
          Antes de autorizar, o cliente precisa cadastrar a URL de retorno abaixo no aplicativo criado dentro da
          conta dele. Ela deve ser idêntica, caractere por caractere.
        </p>
      </header>

      {autorizacaoFalhou && (
        <div className="mb-4 rounded-lg border border-error/20 bg-error-subtle p-3 text-caption-label text-error">
          A autorização não foi concluída. Confira a URL de retorno cadastrada no Tiny e tente novamente.
        </div>
      )}

      <div className="mb-4">
        <label htmlFor="redirect-uri-field" className="mb-2 block text-caption-medium text-muted-foreground">
          URL de retorno (redirect URI)
        </label>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background p-2.5 pl-3.5">
          <input
            id="redirect-uri-field"
            readOnly
            value={redirectUri}
            className="w-full min-w-0 truncate border-0 bg-transparent p-0 font-mono text-caption-label text-foreground outline-none select-all"
          />
          <button
            type="button"
            onClick={copiarRedirectUri}
            className="flex h-7 shrink-0 items-center gap-1.5 rounded border border-border bg-secondary px-3 text-caption-medium font-medium text-foreground transition-colors hover:bg-accent"
          >
            {copiado ? <Check size={14} className="text-success" /> : <Copy size={14} className="text-muted-foreground" />}
            <span className={copiado ? "text-success" : undefined}>{copiado ? "Copiado" : "Copiar"}</span>
          </button>
        </div>
        <p className="mt-2 text-caption-label text-muted-foreground/70">
          Cadastre em <span className="text-muted-foreground">Configurações → Geral → Aplicativos</span>, no ERP do
          cliente.
        </p>
      </div>

      <div className="mt-4 flex items-start gap-3 rounded-lg border border-warning/30 bg-warning-subtle p-3.5">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
        <span className="text-caption-label text-warning">
          Uma barra final a mais ou a menos faz o ERP recusar a autorização.
        </span>
      </div>

      <div className="mt-6 space-y-3">
        {ITENS_CHECKLIST.map((texto, indice) => (
          <label key={texto} className="flex cursor-pointer items-center gap-3 select-none">
            <Checkbox
              checked={checklist[indice]}
              onCheckedChange={(marcado) =>
                setChecklist((atual) => atual.map((valor, i) => (i === indice ? marcado === true : valor)))
              }
            />
            <span className="text-body-default text-foreground">{texto}</span>
          </label>
        ))}
      </div>

      <div className="my-6 border-t border-border" />

      <div className="flex flex-col">
        <div className="flex items-center gap-2.5">
          <span className={`size-2 rounded-full ${estado.cor}`} />
          <span className="text-body-medium text-foreground">{estado.texto}</span>
        </div>
        <p className="mt-0.5 ml-4.5 text-caption-label text-muted-foreground">{estado.detalhe}</p>
      </div>

      <footer className="mt-6 flex items-center justify-between border-t border-border pt-6">
        <Button variant="ghost" onClick={onVoltar}>
          Voltar
        </Button>
        <div className="flex flex-col items-end gap-1.5">
          <Button variant="primary" disabled={!todosMarcados || isAutorizando} onClick={onAutorizar}>
            {isAutorizando ? "Redirecionando…" : "Autorizar no ERP"}
          </Button>
          <span className="text-caption-label text-muted-foreground/70">
            Você será redirecionado para a tela de login do ERP.
          </span>
        </div>
      </footer>
    </div>
  )
}
