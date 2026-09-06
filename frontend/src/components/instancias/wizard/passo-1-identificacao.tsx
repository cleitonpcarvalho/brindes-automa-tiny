"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { WizardCard } from "./wizard-card"

export interface DadosIdentificacao {
  nome: string
  cnpj: string
}

interface Props {
  valorInicial: DadosIdentificacao
  onAvancar: (dados: DadosIdentificacao) => void
}

/** Sem mockup completo (design/04 só detalha o passo 3) — mesmo estilo de card. */
export function Passo1Identificacao({ valorInicial, onAvancar }: Props) {
  const [nome, setNome] = useState(valorInicial.nome)
  const [cnpj, setCnpj] = useState(valorInicial.cnpj)

  return (
    <WizardCard
      titulo="Identificação"
      subtitulo="Nome do cliente e CNPJ, usados na busca da listagem de instâncias."
      footer={
        <>
          <span />
          <Button
            variant="primary"
            disabled={!nome.trim()}
            onClick={() => onAvancar({ nome: nome.trim(), cnpj: cnpj.trim() })}
          >
            Avançar
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="nome">Nome do cliente</Label>
          <Input
            id="nome"
            value={nome}
            onChange={(event) => setNome(event.target.value)}
            placeholder="Ex.: Líder Brindes & Personalizados"
            autoFocus
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cnpj">CNPJ (opcional)</Label>
          <Input
            id="cnpj"
            value={cnpj}
            onChange={(event) => setCnpj(event.target.value)}
            placeholder="00.000.000/0000-00"
          />
        </div>
      </div>
    </WizardCard>
  )
}
