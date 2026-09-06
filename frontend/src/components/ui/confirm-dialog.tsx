"use client"

import * as React from "react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

interface ConfirmDialogProps {
  /** Elemento que abre o dialog ao ser clicado. Omita para controlar a abertura via `open`/`onOpenChange` (ex.: um item de dropdown menu, que já fecha sozinho antes do dialog poder abrir). */
  trigger?: React.ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
  title: string
  description: string
  confirmLabel: string
  destructive?: boolean
  onConfirm: () => unknown | Promise<unknown>
  isLoading?: boolean
}

/** Toda ação destrutiva (desconectar, etc.) passa por aqui — pedido explícito do passo 10. */
export function ConfirmDialog({
  trigger,
  open: openControlado,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = true,
  onConfirm,
  isLoading = false,
}: ConfirmDialogProps) {
  const [openInterno, setOpenInterno] = useState(false)
  const open = openControlado ?? openInterno
  const setOpen = onOpenChange ?? setOpenInterno

  async function handleConfirm() {
    await onConfirm()
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={isLoading}>
            Cancelar
          </Button>
          <Button variant={destructive ? "destructive" : "primary"} onClick={handleConfirm} disabled={isLoading}>
            {isLoading ? "Aguarde…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
