"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { MoreVertical } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useAutorizar, useDesconectar } from "@/lib/api/hooks"

export function AcoesMenu({ slug }: { slug: string }) {
  const router = useRouter()
  const [confirmandoDesconexao, setConfirmandoDesconexao] = useState(false)
  const autorizar = useAutorizar(slug)
  const desconectar = useDesconectar(slug)

  async function handleReautorizar() {
    const resposta = await autorizar.mutateAsync()
    window.location.href = resposta.url_autorizacao
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Ações de instância"
            onClick={(event) => event.stopPropagation()}
          >
            <MoreVertical size={16} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(event) => event.stopPropagation()}>
          <DropdownMenuItem onSelect={() => router.push(`/instancias/${slug}`)}>Ver detalhes</DropdownMenuItem>
          <DropdownMenuItem onSelect={handleReautorizar} disabled={autorizar.isPending}>
            Reautorizar
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault()
              setConfirmandoDesconexao(true)
            }}
          >
            Desconectar
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={confirmandoDesconexao}
        onOpenChange={setConfirmandoDesconexao}
        title="Desconectar instância"
        description="Os tokens de acesso ao Tiny serão apagados. A instância continua cadastrada e pode ser reautorizada depois."
        confirmLabel="Desconectar"
        isLoading={desconectar.isPending}
        onConfirm={() => desconectar.mutateAsync()}
      />
    </>
  )
}
