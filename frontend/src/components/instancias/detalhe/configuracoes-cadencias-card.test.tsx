import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ConfiguracoesCadenciasCard } from "./configuracoes-cadencias-card"
import type { CadenciaFornecedor } from "@/lib/api/types"

vi.mock("@/lib/api/hooks", () => ({
  useCadencias: vi.fn(),
  useAtualizarCadencia: vi.fn(),
}))

const mutate = vi.fn()

function cadencias(): CadenciaFornecedor[] {
  return [
    { fornecedor: "xbz", intervalo_minutos: 60, ativo: true, propagar_tiny: false, proxima_execucao_em: null },
    { fornecedor: "asia", intervalo_minutos: 120, ativo: false, propagar_tiny: false, proxima_execucao_em: null },
    { fornecedor: "somarcas", intervalo_minutos: 240, ativo: false, propagar_tiny: false, proxima_execucao_em: null },
    { fornecedor: "spot", intervalo_minutos: 720, ativo: true, propagar_tiny: true, proxima_execucao_em: null },
  ]
}

function mockCadencias(estado: Record<string, unknown>) {
  vi.mocked(hooks.useCadencias).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    ...estado,
  } as never)
}

describe("ConfiguracoesCadenciasCard", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(hooks.useAtualizarCadencia).mockReturnValue({
      mutate,
      isPending: false,
      error: null,
    } as never)
  })

  it("mostra skeletons durante o carregamento", () => {
    mockCadencias({ isLoading: true })
    const { container } = render(<ConfiguracoesCadenciasCard slug="loja-x" />)
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)
  })

  it("mostra erro com retry", () => {
    const refetch = vi.fn()
    mockCadencias({ isError: true, refetch })
    render(<ConfiguracoesCadenciasCard slug="loja-x" />)
    screen.getByRole("button", { name: "Tentar de novo" }).click()
    expect(refetch).toHaveBeenCalledOnce()
  })

  it("renderiza uma seção por fornecedor com o rótulo e a nota da XBZ", () => {
    mockCadencias({ data: cadencias() })
    render(<ConfiguracoesCadenciasCard slug="loja-x" />)

    expect(screen.getByText("XBZ")).toBeInTheDocument()
    expect(screen.getByText("Asia Import")).toBeInTheDocument()
    expect(screen.getByText("Só Marcas")).toBeInTheDocument()
    expect(screen.getByText("Spot Gifts")).toBeInTheDocument()
    expect(screen.getByText(/24 chamadas por dia/)).toBeInTheDocument()
    // 4 fornecedores × (Sincronização ativa + Refletir no Tiny)
    expect(screen.getAllByRole("switch")).toHaveLength(8)
    expect(screen.getAllByRole("switch", { name: "Refletir no Tiny automaticamente" })).toHaveLength(4)
  })

  it("alterar o Switch de um fornecedor persiste a cadência (sem sincronizar)", () => {
    mockCadencias({ data: cadencias() })
    render(<ConfiguracoesCadenciasCard slug="loja-x" />)

    // asia começa inativo — 2ª seção
    const switchAsia = screen.getAllByRole("switch", { name: "Sincronização ativa" })[1]
    fireEvent.click(switchAsia)
    expect(mutate).toHaveBeenCalledWith({ ativo: true })
  })

  it("liga a propagação ao Tiny de um fornecedor já ativo", () => {
    mockCadencias({ data: cadencias() })
    render(<ConfiguracoesCadenciasCard slug="loja-x" />)

    // spot está ativo e sem propagação — 4ª seção
    const switchSpot = screen.getAllByRole("switch", { name: "Refletir no Tiny automaticamente" })[3]
    expect(switchSpot).toBeChecked()

    // xbz está ativo mas sem propagação — 1ª seção
    const switchXbz = screen.getAllByRole("switch", { name: "Refletir no Tiny automaticamente" })[0]
    fireEvent.click(switchXbz)
    expect(mutate).toHaveBeenCalledWith({ propagar_tiny: true })
  })
})
