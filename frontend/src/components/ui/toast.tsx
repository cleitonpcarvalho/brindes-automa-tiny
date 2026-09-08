"use client"

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react"
import { CheckCircle2, X, XCircle } from "lucide-react"
import { cn } from "cn"

type Tipo = "sucesso" | "erro"

interface Toast {
  id: number
  tipo: Tipo
  mensagem: string
}

interface ToastApi {
  sucesso: (mensagem: string) => void
  erro: (mensagem: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const DURACAO_MS = 6000

/**
 * Toast mínimo (sem dependência externa): um provider no topo da árvore e um
 * `useToast()` que devolve `{ sucesso, erro }`. Auto-some em ~6s; clique fecha.
 * Região `aria-live` para leitores de tela.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const proximoId = useRef(1)

  const remover = useCallback((id: number) => {
    setToasts((atuais) => atuais.filter((toast) => toast.id !== id))
  }, [])

  const adicionar = useCallback(
    (tipo: Tipo, mensagem: string) => {
      const id = proximoId.current++
      setToasts((atuais) => [...atuais, { id, tipo, mensagem }])
      setTimeout(() => remover(id), DURACAO_MS)
    },
    [remover],
  )

  const api = useMemo<ToastApi>(
    () => ({
      sucesso: (mensagem) => adicionar("sucesso", mensagem),
      erro: (mensagem) => adicionar("erro", mensagem),
    }),
    [adicionar],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[min(92vw,380px)] flex-col gap-2"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            onClick={() => remover(toast.id)}
            className={cn(
              "pointer-events-auto flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2.5 text-body-medium shadow-lg",
              toast.tipo === "sucesso"
                ? "border-success/30 bg-success-subtle text-success"
                : "border-error/30 bg-error-subtle text-error",
            )}
          >
            {toast.tipo === "sucesso" ? (
              <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
            ) : (
              <XCircle size={16} className="mt-0.5 shrink-0" />
            )}
            <span className="flex-1 whitespace-normal">{toast.mensagem}</span>
            <X size={14} className="mt-0.5 shrink-0 opacity-60" />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext)
  if (!api) {
    throw new Error("useToast precisa estar dentro de <ToastProvider>")
  }
  return api
}
