import { renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { useInstanciaSelecionada } from "./use-instancia-selecionada"

const replace = vi.fn()
let mockParams = ""

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/sincronizacoes",
  useSearchParams: () => new URLSearchParams(mockParams),
}))

vi.mock("@/lib/api/hooks", () => ({
  useInstanciasListagem: vi.fn(),
}))

function mockLista(results: { slug: string; nome: string }[], extra: Record<string, unknown> = {}) {
  vi.mocked(hooks.useInstanciasListagem).mockReturnValue({
    data: { count: results.length, results },
    isLoading: false,
    isError: false,
    refetch: vi.fn().mockResolvedValue(undefined),
    ...extra,
  } as never)
}

describe("useInstanciaSelecionada", () => {
  beforeEach(() => {
    replace.mockClear()
    mockParams = ""
  })

  it("sem ?instancia: cai na primeira", () => {
    mockLista([{ slug: "a", nome: "A" }, { slug: "b", nome: "B" }])
    const { result } = renderHook(() => useInstanciaSelecionada())
    expect(result.current.slug).toBe("a")
    expect(result.current.unica).toBe(false)
    expect(result.current.vazio).toBe(false)
  })

  it("respeita ?instancia quando o slug existe", () => {
    mockParams = "instancia=b"
    mockLista([{ slug: "a", nome: "A" }, { slug: "b", nome: "B" }])
    const { result } = renderHook(() => useInstanciaSelecionada())
    expect(result.current.slug).toBe("b")
  })

  it("ignora ?instancia inválida e cai na primeira", () => {
    mockParams = "instancia=nao-existe"
    mockLista([{ slug: "a", nome: "A" }])
    const { result } = renderHook(() => useInstanciaSelecionada())
    expect(result.current.slug).toBe("a")
    expect(result.current.unica).toBe(true)
  })

  it("definir() grava o slug no query param via router.replace", () => {
    mockLista([{ slug: "a", nome: "A" }, { slug: "b", nome: "B" }])
    const { result } = renderHook(() => useInstanciaSelecionada())
    result.current.definir("b")
    expect(replace).toHaveBeenCalledWith("/sincronizacoes?instancia=b", { scroll: false })
  })

  it("lista vazia: vazio=true e slug vazio", () => {
    mockLista([])
    const { result } = renderHook(() => useInstanciaSelecionada())
    expect(result.current.vazio).toBe(true)
    expect(result.current.slug).toBe("")
  })

  it("carregando: não marca vazio", () => {
    mockLista([], { isLoading: true, data: undefined })
    const { result } = renderHook(() => useInstanciaSelecionada())
    expect(result.current.isLoading).toBe(true)
    expect(result.current.vazio).toBe(false)
  })
})
