import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ApiError } from "@/lib/api/client"
import { ConfiguracoesTinyCard } from "./configuracoes-tiny-card"

vi.mock("@/lib/api/hooks", () => ({
  useConfiguracoesInstancia: vi.fn(),
  useAtualizarConfiguracoes: vi.fn(),
}))

const mutate = vi.fn()

function mockConfig(data: unknown, extra: Record<string, unknown> = {}) {
  vi.mocked(hooks.useConfiguracoesInstancia).mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    ...extra,
  } as never)
}

function mockMutacao(estado: Partial<{ isPending: boolean; isSuccess: boolean; error: unknown }> = {}) {
  vi.mocked(hooks.useAtualizarConfiguracoes).mockReturnValue({
    mutate,
    isPending: false,
    isSuccess: false,
    error: null,
    ...estado,
  } as never)
}

describe("ConfiguracoesTinyCard", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockMutacao()
  })

  it("carrega os valores atuais do backend", () => {
    mockConfig({ tiny_origem_padrao: 1, tiny_unidade_medida_padrao: "UN" })
    render(<ConfiguracoesTinyCard slug="loja-x" />)

    expect(screen.getByLabelText("Origem padrão do produto")).toHaveValue(1)
    expect(screen.getByDisplayValue("UN")).toBeInTheDocument()
  })

  it("mostra erro com retry quando a leitura falha", () => {
    mockConfig(undefined, { isError: true })
    render(<ConfiguracoesTinyCard slug="loja-x" />)
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument()
  })

  it("mantém Salvar desabilitado enquanto não há alteração", () => {
    mockConfig({ tiny_origem_padrao: 1, tiny_unidade_medida_padrao: "PC" })
    render(<ConfiguracoesTinyCard slug="loja-x" />)
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled()
  })

  it("habilita Salvar após alterar e envia só os campos permitidos", () => {
    mockConfig({ tiny_origem_padrao: null, tiny_unidade_medida_padrao: "" })
    render(<ConfiguracoesTinyCard slug="loja-x" />)

    fireEvent.change(screen.getByLabelText("Unidade de medida padrão"), { target: { value: "CX" } })
    fireEvent.change(screen.getByLabelText("Origem padrão do produto"), { target: { value: "2" } })

    const salvar = screen.getByRole("button", { name: "Salvar" })
    expect(salvar).toBeEnabled()
    fireEvent.click(salvar)
    expect(mutate).toHaveBeenCalledWith({ tiny_origem_padrao: 2, tiny_unidade_medida_padrao: "CX" })
  })

  it("bloqueia o Salvar e mostra erro para origem fora de 0–8", () => {
    mockConfig({ tiny_origem_padrao: null, tiny_unidade_medida_padrao: "" })
    render(<ConfiguracoesTinyCard slug="loja-x" />)

    fireEvent.change(screen.getByLabelText("Origem padrão do produto"), { target: { value: "99" } })
    expect(screen.getByText("Informe um número inteiro de 0 a 8.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled()
    expect(mutate).not.toHaveBeenCalled()
  })

  it("mostra o feedback de sucesso quando salvou e não há alteração pendente", () => {
    mockConfig({ tiny_origem_padrao: 2, tiny_unidade_medida_padrao: "UN" })
    mockMutacao({ isSuccess: true })
    render(<ConfiguracoesTinyCard slug="loja-x" />)
    expect(screen.getByText("Configurações salvas.")).toBeInTheDocument()
  })

  it("mostra a mensagem de erro da API", () => {
    mockConfig({ tiny_origem_padrao: null, tiny_unidade_medida_padrao: "" })
    mockMutacao({ error: new ApiError(400, "Origem inválida.") })
    render(<ConfiguracoesTinyCard slug="loja-x" />)
    expect(screen.getByText("Origem inválida.")).toBeInTheDocument()
  })
})
