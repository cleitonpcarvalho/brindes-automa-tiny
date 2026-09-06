import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as selHook from "./use-instancia-selecionada"
import { ConfiguracoesGlobaisView } from "./configuracoes-globais-view"

vi.mock("./use-instancia-selecionada", () => ({ useInstanciaSelecionada: vi.fn() }))
vi.mock("@/components/instancias/detalhe/configuracoes-tab", () => ({
  ConfiguracoesTab: ({ slug }: { slug: string }) => <div data-testid="configuracoes-tab">config de {slug}</div>,
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

describe("ConfiguracoesGlobaisView", () => {
  beforeEach(() => vi.clearAllMocks())

  it("uma instância: subtítulo direto e mostra as configurações dela", () => {
    mockSel({ slug: "ekk", unica: true, instancias: [{ slug: "ekk", nome: "EKK" }] as never })
    render(<ConfiguracoesGlobaisView />)
    expect(screen.getByText("Configurações operacionais da instância.")).toBeInTheDocument()
    expect(screen.getByTestId("configuracoes-tab")).toHaveTextContent("config de ekk")
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument()
  })

  it("várias instâncias: subtítulo de escolha + seletor + configurações da selecionada", () => {
    mockSel({
      slug: "b",
      unica: false,
      instancias: [{ slug: "a", nome: "Loja A" }, { slug: "b", nome: "Loja B" }] as never,
    })
    render(<ConfiguracoesGlobaisView />)
    expect(screen.getByText(/Escolha uma instância/)).toBeInTheDocument()
    expect(screen.getByRole("combobox")).toHaveTextContent("Loja B")
    expect(screen.getByTestId("configuracoes-tab")).toHaveTextContent("config de b")
  })

  it("vazio: convida a criar instância", () => {
    mockSel({ vazio: true })
    render(<ConfiguracoesGlobaisView />)
    expect(screen.getByText("Nenhuma instância cadastrada")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Criar instância" })).toHaveAttribute("href", "/instancias/novo")
    expect(screen.queryByTestId("configuracoes-tab")).not.toBeInTheDocument()
  })

  it("erro: ErrorState com retry", () => {
    const refetch = vi.fn()
    mockSel({ isError: true, refetch })
    render(<ConfiguracoesGlobaisView />)
    screen.getByRole("button", { name: "Tentar de novo" }).click()
    expect(refetch).toHaveBeenCalledOnce()
  })
})
