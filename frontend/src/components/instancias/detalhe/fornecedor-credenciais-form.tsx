"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api/client"
import { useAtualizarCredencial } from "@/lib/api/hooks"
import { CAMPOS_CREDENCIAL } from "./campos-credencial"
import type { CredencialFornecedorResposta, FornecedorEnum } from "@/lib/api/types"

interface Props {
  fornecedor: FornecedorEnum
  credencial: CredencialFornecedorResposta
  slug: string
}

export function FornecedorCredenciaisForm({ fornecedor, credencial, slug }: Props) {
  const [editando, setEditando] = useState(false)
  const [valores, setValores] = useState<Record<string, string>>({})
  const atualizar = useAtualizarCredencial(slug, fornecedor)
  const campos = CAMPOS_CREDENCIAL[fornecedor]

  function iniciarEdicao() {
    setValores({})
    atualizar.reset()
    setEditando(true)
  }

  async function salvar() {
    await atualizar.mutateAsync({ credenciais: valores, ativo: credencial.ativo })
    setEditando(false)
  }

  const podeSalvar = campos.filter((c) => c.obrigatorio).every((c) => valores[c.chave]?.trim())
  const mensagemErro = atualizar.error instanceof ApiError ? atualizar.error.message : null

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-caption-medium tracking-wide text-muted-foreground uppercase">Credenciais</h3>

      {campos.map((campo) => (
        <div key={campo.chave} className="flex flex-col gap-1.5">
          <Label htmlFor={`${fornecedor}-${campo.chave}`}>{campo.rotulo}</Label>
          {editando ? (
            <Input
              id={`${fornecedor}-${campo.chave}`}
              type={campo.sensivel ? "password" : "text"}
              value={valores[campo.chave] ?? ""}
              onChange={(event) => setValores((atual) => ({ ...atual, [campo.chave]: event.target.value }))}
              placeholder={campo.obrigatorio ? undefined : "opcional"}
              className="font-mono"
            />
          ) : (
            <Input
              readOnly
              value={String(credencial.campos_mascarados[campo.chave] ?? "Não configurado")}
              className="font-mono text-muted-foreground"
            />
          )}
        </div>
      ))}

      {editando ? (
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setEditando(false)} disabled={atualizar.isPending}>
            Cancelar
          </Button>
          <Button variant="primary" size="sm" onClick={salvar} disabled={!podeSalvar || atualizar.isPending}>
            {atualizar.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      ) : (
        <Button variant="secondary" size="sm" className="w-fit" onClick={iniciarEdicao}>
          Editar
        </Button>
      )}

      {mensagemErro && <p className="text-caption-label text-error">{mensagemErro}</p>}
    </div>
  )
}
