"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { WizardCard } from "./wizard-card"

export interface DadosCredenciaisTiny {
  client_id: string
  client_secret: string
}

interface Props {
  valorInicial: DadosCredenciaisTiny
  clientSecretJaConfigurado: boolean
  isSubmitting: boolean
  erro: string | null
  onVoltar: () => void
  onAvancar: (dados: DadosCredenciaisTiny) => void
}

/** Sem mockup completo (design/04 só detalha o passo 3) — mesmo estilo de card. */
export function Passo2Credenciais({
  valorInicial,
  clientSecretJaConfigurado,
  isSubmitting,
  erro,
  onVoltar,
  onAvancar,
}: Props) {
  const [clientId, setClientId] = useState(valorInicial.client_id)
  const [clientSecret, setClientSecret] = useState("")

  const podeAvancar = clientId.trim() && (clientSecretJaConfigurado || clientSecret.trim())

  return (
    <WizardCard
      titulo="Credenciais"
      subtitulo="Client ID e Client Secret do aplicativo criado na conta do cliente no Tiny."
      footer={
        <>
          <Button variant="ghost" onClick={onVoltar} disabled={isSubmitting}>
            Voltar
          </Button>
          <Button
            variant="primary"
            disabled={!podeAvancar || isSubmitting}
            onClick={() => onAvancar({ client_id: clientId.trim(), client_secret: clientSecret.trim() })}
          >
            {isSubmitting ? "Salvando…" : "Avançar"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="client_id">Client ID</Label>
          <Input
            id="client_id"
            value={clientId}
            onChange={(event) => setClientId(event.target.value)}
            className="font-mono"
            autoFocus
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="client_secret">Client Secret</Label>
          <Input
            id="client_secret"
            type="password"
            value={clientSecret}
            onChange={(event) => setClientSecret(event.target.value)}
            placeholder={clientSecretJaConfigurado ? "Já configurado — deixe em branco para manter" : undefined}
            className="font-mono"
          />
        </div>
        {erro && <p className="text-caption-label text-error">{erro}</p>}
      </div>
    </WizardCard>
  )
}
