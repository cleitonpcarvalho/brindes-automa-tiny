"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { ApiError } from "@/lib/api/client"
import { useAtualizarCredencial } from "@/lib/api/hooks"
import { CAMPOS_CREDENCIAL } from "./campos-credencial"
import type { CredencialFornecedorResposta, FornecedorEnum } from "@/lib/api/types"

/** Estado `ativo` que uma edição deve começar: credencial nova nasce ativa. */
function ativoInicial(credencial: CredencialFornecedorResposta) {
  return credencial.configurado ? credencial.ativo : true
}

interface Props {
  fornecedor: FornecedorEnum
  credencial: CredencialFornecedorResposta
  slug: string
}

export function FornecedorCredenciaisForm({ fornecedor, credencial, slug }: Props) {
  const [editando, setEditando] = useState(false)
  const [valores, setValores] = useState<Record<string, string>>({})
  const [ativo, setAtivo] = useState(() => ativoInicial(credencial))
  const [mensagemErro, setMensagemErro] = useState<string | null>(null)
  const atualizar = useAtualizarCredencial(slug, fornecedor)
  const campos = CAMPOS_CREDENCIAL[fornecedor]
  const podeSalvar = campos.filter((c) => c.obrigatorio).every((c) => valores[c.chave]?.trim())
  const instrucaoSecretsId = `${slug}-${fornecedor}-secrets`
  const ativoAtual = editando ? ativo : credencial.ativo

  function iniciarEdicao() {
    setValores(Object.fromEntries(campos.map((campo) => {
      const valor = credencial.campos_mascarados[campo.chave]
      return [campo.chave, !campo.sensivel && typeof valor === "string" ? valor : ""]
    })))
    setAtivo(ativoInicial(credencial))
    setMensagemErro(null)
    atualizar.reset()
    setEditando(true)
  }

  function encerrarEdicao() {
    setValores({})
    setAtivo(ativoInicial(credencial))
    setMensagemErro(null)
    atualizar.reset()
    setEditando(false)
  }

  async function salvar() {
    if (!editando || atualizar.isPending) return
    if (!podeSalvar) {
      setMensagemErro("Preencha todos os campos obrigatórios.")
      return
    }

    setMensagemErro(null)
    try {
      // O PUT substitui o conjunto completo; máscaras nunca entram no payload.
      // `ativo` vai SEMPRE explícito, com o valor do controle "Credencial ativa"
      // (nova nasce marcada; existente inativa pode ser ativada aqui). Isso é a
      // credencial poder ser usada para importar — NÃO é a cadência/sincronização
      // automática, que tem o próprio switch em "Sincronização".
      await atualizar.mutateAsync({ credenciais: valores, ativo })
      encerrarEdicao()
    } catch (erro) {
      setMensagemErro(erro instanceof ApiError
        ? erro.status === 400
          ? "Confira os campos obrigatórios e informe novamente todos os campos secretos."
          : erro.message
        : "Não foi possível salvar as credenciais. Verifique sua conexão e tente novamente.")
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); void salvar() }}>
      <h3 className="text-caption-medium tracking-wide text-muted-foreground uppercase">Credenciais</h3>

      {editando && (
        <p id={instrucaoSecretsId} className="text-caption-label text-muted-foreground">
          Para salvar, informe novamente todos os campos secretos. Os valores atuais não são exibidos.
        </p>
      )}

      {campos.map((campo) => (
        <div key={campo.chave} className="flex flex-col gap-1.5">
          <Label htmlFor={`${slug}-${fornecedor}-${campo.chave}`}>{campo.rotulo}</Label>
          <Input
            id={`${slug}-${fornecedor}-${campo.chave}`}
            type={editando && campo.sensivel ? "password" : "text"}
            readOnly={!editando}
            disabled={atualizar.isPending}
            required={editando && campo.obrigatorio}
            autoComplete={campo.sensivel ? "new-password" : "off"}
            aria-describedby={editando && campo.sensivel ? instrucaoSecretsId : undefined}
            value={editando
              ? valores[campo.chave] ?? ""
              : String(credencial.campos_mascarados[campo.chave] || "Não configurado")}
            onChange={(event) => setValores((atual) => ({ ...atual, [campo.chave]: event.target.value }))}
            placeholder={editando && !campo.obrigatorio ? "opcional" : undefined}
            className={editando ? "font-mono" : "font-mono text-muted-foreground"}
          />
        </div>
      ))}

      <div className="flex items-start justify-between gap-4 pt-1">
        <div>
          <p className="text-body-medium text-foreground">Credencial ativa</p>
          <p className="text-caption-label text-muted-foreground">
            Permite usar esta credencial para importar o catálogo do fornecedor. Não é a
            sincronização automática (essa fica em &ldquo;Sincronização&rdquo;).
          </p>
          {!editando && credencial.configurado && !credencial.ativo && (
            <p className="mt-1 text-caption-label text-error">
              Inativa — clique em &ldquo;Editar&rdquo; para ativar.
            </p>
          )}
        </div>
        <Switch
          aria-label="Credencial ativa"
          checked={ativoAtual}
          disabled={!editando || atualizar.isPending}
          onCheckedChange={setAtivo}
        />
      </div>

      {editando ? (
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={encerrarEdicao} disabled={atualizar.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={!podeSalvar || atualizar.isPending}>
            {atualizar.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      ) : (
        <Button type="button" variant="secondary" size="sm" className="w-fit" onClick={iniciarEdicao}>
          Editar
        </Button>
      )}

      {mensagemErro && <p role="alert" className="text-caption-label text-error">{mensagemErro}</p>}
    </form>
  )
}
