"use client"

import { useCallback, useMemo } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useInstanciasListagem } from "@/lib/api/hooks"
import type { InstanciaListagem } from "@/lib/api/types"

const PARAM = "instancia"

export interface InstanciaSelecionada {
  isLoading: boolean
  isError: boolean
  refetch: () => void
  instancias: InstanciaListagem[]
  /** slug atualmente selecionado; "" enquanto carrega ou se não há instâncias. */
  slug: string
  /** só existe uma instância acessível — o seletor vira um rótulo estático. */
  unica: boolean
  /** carregou sem erro e não há nenhuma instância. */
  vazio: boolean
  definir: (slug: string) => void
}

/**
 * Instância "ativa" das telas globais (/sincronizacoes, /logs, /configuracoes).
 * Reaproveita `useInstanciasListagem` — as telas globais são as mesmas da
 * instância, só que com um seletor por cima. A escolha vive no query param
 * `?instancia=<slug>` para ser compartilhável e sobreviver a refresh; quando
 * ausente ou inválida, cai na primeira instância.
 */
export function useInstanciaSelecionada(): InstanciaSelecionada {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const { data, isLoading, isError, refetch } = useInstanciasListagem({ pageSize: 100 })

  const instancias = useMemo(() => data?.results ?? [], [data])

  const pedido = searchParams.get(PARAM) ?? ""
  const slug = instancias.some((i) => i.slug === pedido) ? pedido : (instancias[0]?.slug ?? "")

  const definir = useCallback(
    (novoSlug: string) => {
      const params = new URLSearchParams(searchParams.toString())
      params.set(PARAM, novoSlug)
      router.replace(`${pathname}?${params.toString()}`, { scroll: false })
    },
    [router, pathname, searchParams],
  )

  return {
    isLoading,
    isError,
    refetch: () => {
      void refetch()
    },
    instancias,
    slug,
    unica: instancias.length === 1,
    vazio: !isLoading && !isError && instancias.length === 0,
    definir,
  }
}
