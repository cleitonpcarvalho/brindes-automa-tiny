"use client"

import { Loader2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { ApiError } from "@/lib/api/client"
import { useRetentarVariacaoExecucao } from "@/lib/api/hooks"
import type { ExecucaoProduto } from "@/lib/api/types"

/**
 * "Tentar novamente" de UMA linha (SKU com erro) da tela de detalhe de
 * Execução. Só aparece para `resultado === "erro"` e com `variacao_id`. O
 * loading é local à linha; o botão fica `disabled` enquanto o POST está em
 * voo (protege contra clique duplo). Toast de sucesso/erro sem mascarar o
 * erro real; a linha e os contadores são atualizados pelo hook, sem recarregar.
 */
export function RetentarBotao({
  slug,
  execucaoId,
  linha,
  disabled,
}: {
  slug: string
  execucaoId: string
  linha: ExecucaoProduto
  disabled?: boolean
}) {
  const toast = useToast()
  const retentar = useRetentarVariacaoExecucao(slug, execucaoId)

  if (linha.resultado !== "erro" || linha.variacao_id == null) return null

  function tentar() {
    if (retentar.isPending || disabled || linha.variacao_id == null) return
    retentar.mutate(linha.variacao_id, {
      onSuccess: (nova) => toast.sucesso(`SKU ${nova.sku} cadastrado no Tiny.`),
      onError: (erro) =>
        toast.erro(
          erro instanceof ApiError
            ? erro.message
            : `Não foi possível recadastrar o SKU ${linha.sku}.`,
        ),
    })
  }

  return (
    <Button
      variant="secondary"
      size="sm"
      aria-label={`Tentar cadastrar o SKU ${linha.sku} novamente`}
      disabled={retentar.isPending || disabled}
      onClick={tentar}
    >
      {retentar.isPending ? (
        <Loader2 size={14} className="animate-spin" />
      ) : (
        <RefreshCw size={14} />
      )}
      {retentar.isPending ? "Tentando…" : "Tentar novamente"}
    </Button>
  )
}
