import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { FornecedorCadenciaForm } from "./fornecedor-cadencia-form"
import type { CadenciaFornecedor } from "@/lib/api/types"

vi.mock("@/lib/api/hooks", () => ({ useAtualizarCadencia: vi.fn() }))

const mutate = vi.fn()

function cadencia(over: Partial<CadenciaFornecedor> = {}): CadenciaFornecedor {
  return { fornecedor: "asia", intervalo_minutos: 60, ativo: true, propagar_tiny: false, proxima_execucao_em: null, ...over }
}

function renderForm(over: Partial<CadenciaFornecedor> = {}) {
  render(<FornecedorCadenciaForm fornecedor="asia" cadencia={cadencia(over)} slug="loja-x" />)
}

describe("FornecedorCadenciaForm — 'Refletir no Tiny automaticamente'", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(hooks.useAtualizarCadencia).mockReturnValue({ mutate, isPending: false, error: null } as never)
  })

  it("o switch reflete propagar_tiny e dispara a mutation", () => {
    renderForm({ propagar_tiny: false })
    const sw = screen.getByRole("switch", { name: "Refletir no Tiny automaticamente" })
    expect(sw).not.toBeChecked()
    fireEvent.click(sw)
    expect(mutate).toHaveBeenCalledWith({ propagar_tiny: true })
  })

  it("vem marcado quando propagar_tiny é true", () => {
    renderForm({ propagar_tiny: true })
    expect(screen.getByRole("switch", { name: "Refletir no Tiny automaticamente" })).toBeChecked()
  })

  it("fica desabilitado enquanto a sincronização não estiver ativa", () => {
    renderForm({ ativo: false, propagar_tiny: false })
    expect(screen.getByRole("switch", { name: "Refletir no Tiny automaticamente" })).toBeDisabled()
  })

  it("é um controle distinto de 'Sincronização ativa'", () => {
    renderForm()
    fireEvent.click(screen.getByRole("switch", { name: "Sincronização ativa" }))
    expect(mutate).toHaveBeenCalledWith({ ativo: false })
    expect(mutate).not.toHaveBeenCalledWith(expect.objectContaining({ propagar_tiny: expect.anything() }))
  })
})
