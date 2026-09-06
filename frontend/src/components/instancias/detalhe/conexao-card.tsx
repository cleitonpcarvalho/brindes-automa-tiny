"use client"

import { cn } from "cn"
import { AlertTriangle, KeyRound } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useAutorizar, useDesconectar } from "@/lib/api/hooks"
import { formatarExpiracaoToken, formatarTempoRelativo } from "@/lib/format"
import type { InstanciaDetalhe } from "@/lib/api/types"

// Espelha Instancia.MAX_TENTATIVAS_FALHA_RENOVACAO (backend/apps/instancias/models.py) —
// só para exibição; a regra de verdade vive no backend.
const MAX_TENTATIVAS_FALHA_RENOVACAO = 3

export function ConexaoCard({ instancia, slug }: { instancia: InstanciaDetalhe; slug: string }) {
  const autorizar = useAutorizar(slug)
  const desconectar = useDesconectar(slug)

  const emErro = instancia.status === "erro"
  const token = formatarExpiracaoToken(instancia.token_expira_em)

  async function handleReautorizar() {
    const resposta = await autorizar.mutateAsync()
    window.location.href = resposta.url_autorizacao
  }

  return (
    <div className={cn("relative overflow-hidden rounded-xl bg-card p-4", emErro && "bg-error-subtle/40")}>
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              {emErro && <AlertTriangle size={18} className="text-error" />}
              <span className="text-header-section text-foreground">Conexão com o Tiny</span>
            </div>
            {emErro && <Badge variant="error">Token expirado</Badge>}
          </div>

          <div className="grid grid-cols-2 gap-x-8 gap-y-1 md:grid-cols-4">
            <div className="flex flex-col">
              <span className="text-caption-label text-muted-foreground">Client ID</span>
              <span className="w-fit truncate rounded bg-muted px-1.5 py-0.5 font-mono text-code-inline text-muted-foreground">
                {instancia.client_id || "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-caption-label text-muted-foreground">Token</span>
              <span className={cn("text-body-default", emErro ? "text-error" : "text-foreground")}>
                {token.texto}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-caption-label text-muted-foreground">Última renovação</span>
              <span className="text-body-default text-foreground">
                {formatarTempoRelativo(instancia.token_emitido_em)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-caption-label text-muted-foreground">Tentativas automáticas</span>
              <span className={cn("text-body-default", emErro ? "text-error" : "text-foreground")}>
                {instancia.tentativas_falha} de {MAX_TENTATIVAS_FALHA_RENOVACAO}
                {instancia.tentativas_falha >= MAX_TENTATIVAS_FALHA_RENOVACAO ? " esgotadas" : ""}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start lg:self-center">
          <Button variant={emErro ? "destructive" : "secondary"} onClick={handleReautorizar} disabled={autorizar.isPending}>
            <KeyRound size={14} />
            {autorizar.isPending ? "Gerando…" : "Reautorizar"}
          </Button>
          <ConfirmDialog
            trigger={<Button variant="ghost">Desconectar</Button>}
            title="Desconectar instância"
            description="Os tokens de acesso ao Tiny serão apagados. A instância continua cadastrada e pode ser reautorizada depois."
            confirmLabel="Desconectar"
            isLoading={desconectar.isPending}
            onConfirm={() => desconectar.mutateAsync()}
          />
        </div>
      </div>
    </div>
  )
}
