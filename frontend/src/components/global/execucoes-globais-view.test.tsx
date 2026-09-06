import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as selHook from "./use-instancia-selecionada"
import { ExecucoesGlobaisView } from "./execucoes-globais-view"

vi.mock("./use-instancia-selecionada", () => ({ useInstanciaSelecionada: vi.fn() }))
vi.mock("@/components/instancias/detalhe/execucoes-tab", () => ({
  ExecucoesTab: ({ slug }: { slug: string }) => <div data-testid="execucoes-tab">execucoes de {slug}</div>,
}))

function mockSel(over: Partial<selHook.InstanciaSelecionada>) {
  vi.mocked(selHook.useInstanciaSelecionada).mockReturnValue({
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    instancias: [],
    slug: "",
    unica: false,
    vazio: false,
    definir: vi.fn(),
    ...over,
  })
}

describe("ExecucoesGlobaisView", () => {
  beforeEach(() => vi.clearAllMocks())

  it("variante sincronizacoes: título e subtítulo próprios", () => {
    mockSel({ isLoading: true })
    render(<ExecucoesGlobaisView variante="sincronizacoes" />)
    expect(screen.getByRole("heading", { name: "Sincronizações" })).toBeInTheDocument()
    expect(screen.getByText(/Histórico das rodadas de sincronização/)).toBeInTheDocument()
  })

  it("variante logs: título e subtítulo próprios", () => {
    mockSel({ isLoading: true })
    render(<ExecucoesGlobaisView variante="logs" />)
    expect(screen.getByRole("heading", { name: "Logs" })).toBeInTheDocument()
    expect(screen.getByText(/inspecionar os logs detalhados/)).toBeInTheDocument()
  })

  it("erro: mostra ErrorState com retry", () => {
    const refetch = vi.fn()
    mockSel({ isError: true, refetch })
    render(<ExecucoesGlobaisView variante="sincronizacoes" />)
    screen.getByRole("button", { name: "Tentar de novo" }).click()
    expect(refetch).toHaveBeenCalledOnce()
  })

  it("vazio: convida a criar instância e NÃO renderiza a aba de execuções", () => {
    mockSel({ vazio: true })
    render(<ExecucoesGlobaisView variante="sincronizacoes" />)
    expect(screen.getByText("Nenhuma instância cadastrada")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Criar instância" })).toHaveAttribute("href", "/instancias/novo")
    expect(screen.queryByTestId("execucoes-tab")).not.toBeInTheDocument()
  })

  it("ok: renderiza a ExecucoesTab reaproveitada com o slug selecionado", () => {
    mockSel({
      slug: "ekk",
      instancias: [{ slug: "ekk", nome: "EKK" }, { slug: "b", nome: "B" }] as never,
    })
    render(<ExecucoesGlobaisView variante="sincronizacoes" />)
    expect(screen.getByTestId("execucoes-tab")).toHaveTextContent("execucoes de ekk")
    expect(screen.getByRole("combobox")).toHaveTextContent("EKK")
  })
})
