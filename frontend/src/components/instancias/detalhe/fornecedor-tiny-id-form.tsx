"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api/client"
import { useAtualizarTinyFornecedorId } from "@/lib/api/hooks"
import type { CredencialFornecedorResposta, FornecedorEnum } from "@/lib/api/types"

interface Props {
  fornecedor: FornecedorEnum
  credencial: CredencialFornecedorResposta
  slug: string
}

/**
 * "ID do fornecedor no Tiny" — id do contato/fornecedor na conta Tiny desta
 * instância. NÃO é credencial: valor em texto pleno, endpoint próprio, e um PUT
 * de credenciais nunca o toca. Sem ele, o cadastro de novos produtos desse
 * fornecedor no Tiny fica bloqueado (a tela de "Sincronizar com Tiny" avisa).
 */
export function FornecedorTinyIdForm({ fornecedor, credencial, slug }: Props) {
  const [editando, setEditando] = useState(false)
  const [valor, setValor] = useState("")
  const [mensagemErro, setMensagemErro] = useState<string | null>(null)
  const atualizar = useAtualizarTinyFornecedorId(slug, fornecedor)
  const inputId = `${slug}-${fornecedor}-tiny-fornecedor-id`
  const atual = credencial.tiny_fornecedor_id

  function iniciarEdicao() {
    setValor(atual != null ? String(atual) : "")
    setMensagemErro(null)
    atualizar.reset()
    setEditando(true)
  }

  function encerrarEdicao() {
    setValor("")
    setMensagemErro(null)
    atualizar.reset()
    setEditando(false)
  }

  async function salvar() {
    if (!editando || atualizar.isPending) return
    const limpo = valor.trim()
    if (limpo !== "" && !/^\d+$/.test(limpo)) {
      setMensagemErro("Informe apenas números (o id do fornecedor no Tiny) ou deixe em branco para limpar.")
      return
    }

    setMensagemErro(null)
    try {
      await atualizar.mutateAsync(limpo === "" ? null : Number(limpo))
      encerrarEdicao()
    } catch (erro) {
      setMensagemErro(
        erro instanceof ApiError
          ? erro.status === 400
            ? "O Tiny recusou esse id. Confira o número do contato/fornecedor."
            : erro.message
          : "Não foi possível salvar. Verifique sua conexão e tente novamente.",
      )
    }
  }

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        void salvar()
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={inputId}>ID do fornecedor no Tiny</Label>
        <Input
          id={inputId}
          inputMode="numeric"
          readOnly={!editando}
          disabled={atualizar.isPending}
          value={editando ? valor : atual != null ? String(atual) : "Não configurado"}
          onChange={(event) => setValor(event.target.value)}
          placeholder={editando ? "ex.: 752133514 (em branco = limpar)" : undefined}
          className={editando ? "font-mono" : "font-mono text-muted-foreground"}
        />
      </div>

      <p className="text-caption-label text-muted-foreground">
        Contato/fornecedor correspondente na conta Tiny desta instância. Sem ele, o cadastro de
        novos produtos deste fornecedor no Tiny fica bloqueado.
      </p>

      {!editando && atual == null && (
        <p className="text-caption-label text-error">Não configurado — o cadastro no Tiny fica bloqueado.</p>
      )}

      {editando ? (
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Cancelar edição do ID do fornecedor no Tiny"
            onClick={encerrarEdicao}
            disabled={atualizar.isPending}
          >
            Cancelar
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="sm"
            aria-label="Salvar ID do fornecedor no Tiny"
            disabled={atualizar.isPending}
          >
            {atualizar.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="w-fit"
          aria-label="Editar ID do fornecedor no Tiny"
          onClick={iniciarEdicao}
        >
          Editar
        </Button>
      )}

      {mensagemErro && (
        <p role="alert" className="text-caption-label text-error">
          {mensagemErro}
        </p>
      )}
    </form>
  )
}
