"use client"

import { Loader2, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { ApiError } from "@/lib/api/client"
import { useCadastrarVariacaoTiny } from "@/lib/api/hooks"
import type { VariacaoEspelho } from "@/lib/api/types"

/**
 * Ação discreta "Enviar ao Tiny" de UMA linha da tabela de Produtos. Só
 * aparece para variação `pendente`. O carregamento é local à linha; o botão
 * fica desabilitado enquanto o POST está em voo (protege contra clique
 * duplo). Toast de sucesso/erro; a linha é atualizada pelo hook, sem
 * recarregar a página. Erro do backend NÃO é mascarado.
 */
export function EnviarAoTinyBotao({
  slug,
  variacao,
}: {
  slug: string
  variacao: VariacaoEspelho
}) {
  const toast = useToast()
  const cadastrar = useCadastrarVariacaoTiny(slug)

  if (variacao.status !== "pendente") return null

  function enviar() {
    if (cadastrar.isPending) return
    cadastrar.mutate(variacao.id, {
      onSuccess: () => toast.sucesso(`SKU ${variacao.sku} cadastrado no Tiny.`),
      onError: (erro) =>
        toast.erro(
          erro instanceof ApiError
            ? erro.message
            : `Não foi possível enviar o SKU ${variacao.sku} ao Tiny.`,
        ),
    })
  }

  return (
    <Button
      variant="secondary"
      size="sm"
      aria-label={`Enviar o SKU ${variacao.sku} ao Tiny`}
      disabled={cadastrar.isPending}
      onClick={(evento) => {
        // A linha inteira é um link para o detalhe — não deixa o clique subir.
        evento.stopPropagation()
        enviar()
      }}
    >
      {cadastrar.isPending ? (
        <Loader2 size={14} className="animate-spin" />
      ) : (
        <Send size={14} />
      )}
      {cadastrar.isPending ? "Enviando…" : "Enviar ao Tiny"}
    </Button>
  )
}
