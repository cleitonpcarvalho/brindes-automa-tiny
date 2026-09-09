import type { ComponentProps } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ToastProvider } from "@/components/ui/toast"
import { ExecucaoProdutosTabela } from "./execucao-produtos-tabela"
import type { ExecucaoProduto } from "@/lib/api/types"

const push = vi.fn()
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }))
vi.mock("@/lib/api/hooks", () => ({
  useExecucaoProdutoLogs: vi.fn(),
  useRetentarVariacaoExecucao: vi.fn(),
}))

const retentarMutate = vi.fn()

function linha(over: Partial<ExecucaoProduto> = {}): ExecucaoProduto {
  return {
    log_id: 1,
    variacao_id: 42,
    sku: "MC511",
    codigo_fornecedor: "MC511",
    sku_tiny: "MC511",
    produto_nome: "Mochila para notebook",
    resultado: "criado",
    tiny_id: "924252038",
    mensagem: "SKU MC511 criado no Tiny",
    detalhe_curto: "",
    imagens: null,
    criado_em: "2026-01-01T00:00:00Z",
    ...over,
  }
}

function renderTabela(props: Partial<ComponentProps<typeof ExecucaoProdutosTabela>> = {}) {
  return render(
    <ToastProvider>
      <ExecucaoProdutosTabela
        slug="loja-x"
        execucaoId="7"
        itens={[]}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
        temFiltros={false}
        {...props}
      />
    </ToastProvider>,
  )
}

describe("ExecucaoProdutosTabela", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(hooks.useExecucaoProdutoLogs).mockReturnValue({
      data: { results: [] },
      isLoading: false,
      isError: false,
    } as never)
    vi.mocked(hooks.useRetentarVariacaoExecucao).mockReturnValue({
      mutate: retentarMutate,
      isPending: false,
    } as never)
  })

  it("cadastrado: badge 'Cadastrado' + Tiny ID visível", () => {
    renderTabela({ itens: [linha({ resultado: "criado", tiny_id: "924252038" })] })
    expect(screen.getByText("Cadastrado")).toBeInTheDocument()
    expect(screen.getByText("924252038")).toBeInTheDocument()
  })

  it("XBZ exibe o código fornecedor separado do SKU Tiny", () => {
    renderTabela({
      itens: [
        linha({
          sku: "X134066",
          codigo_fornecedor: "X134066",
          sku_tiny: "18700-AZU",
          produto_nome: "Caneca térmica 500ml",
        }),
      ],
    })

    expect(screen.getByText("X134066")).toBeInTheDocument()
    const produto = screen.getByRole("button", { name: /18700-AZUCaneca térmica 500ml/ })
    expect(produto).toHaveTextContent("18700-AZU")
    expect(produto).not.toHaveTextContent("X134066")
  })

  it("não usa o código fornecedor como fallback de SKU Tiny", () => {
    renderTabela({
      itens: [linha({ sku: "X134066", codigo_fornecedor: "X134066", sku_tiny: "" })],
    })

    const produto = screen.getByRole("button", { name: /—Mochila para notebook/ })
    expect(produto).not.toHaveTextContent("X134066")
  })

  it("erro: badge 'Erro' + mensagem humana curta na coluna Detalhe/erro (sem JSON)", () => {
    renderTabela({
      itens: [
        linha({
          resultado: "erro",
          tiny_id: "",
          detalhe_curto: "Tiny retornou 400: descricao obrigatória",
          mensagem: "Falha ao sincronizar SKU MC511",
        }),
      ],
    })
    expect(screen.getByText("Erro")).toBeInTheDocument()
    expect(screen.getByText("Tiny retornou 400: descricao obrigatória")).toBeInTheDocument()
    expect(screen.queryByText(/[{}]/)).not.toBeInTheDocument()
  })

  it("bloqueado e já cadastrado têm rótulos distintos", () => {
    renderTabela({
      itens: [
        linha({ log_id: 1, sku: "A", resultado: "bloqueado", detalhe_curto: "SKU já existe no Tiny" }),
        linha({ log_id: 2, sku: "B", resultado: "vinculado", tiny_id: "555" }),
      ],
    })
    expect(screen.getByText("Ignorado / bloqueado")).toBeInTheDocument()
    expect(screen.getByText("Já cadastrado")).toBeInTheDocument()
  })

  it("'Ver produto' e o clique no SKU levam para a Variacao correta", () => {
    renderTabela({
      itens: [linha({ variacao_id: 99, sku: "SKU-99", codigo_fornecedor: "SKU-99", sku_tiny: "SKU-99" })],
    })
    fireEvent.click(screen.getByRole("button", { name: "Ver produto" }))
    expect(push).toHaveBeenCalledWith("/instancias/loja-x/produtos/99")

    push.mockClear()
    fireEvent.click(screen.getByRole("button", { name: /SKU-99/ }))
    expect(push).toHaveBeenCalledWith("/instancias/loja-x/produtos/99")
  })

  it("expandir a linha busca e mostra os logs técnicos daquele SKU", () => {
    vi.mocked(hooks.useExecucaoProdutoLogs).mockReturnValue({
      data: {
        results: [
          {
            id: 1,
            nivel: "erro",
            evento: "erro",
            mensagem: "Falha ao sincronizar SKU MC511",
            detalhe: { erro: "Tiny retornou 400" },
            criado_em: "2026-01-01T00:00:00Z",
            variacao_sku: "MC511",
            variacao: 42,
          },
        ],
      },
      isLoading: false,
      isError: false,
    } as never)
    renderTabela({ itens: [linha({ resultado: "erro" })] })

    fireEvent.click(screen.getByRole("button", { name: "Ver mensagem técnica completa" }))
    expect(hooks.useExecucaoProdutoLogs).toHaveBeenCalledWith("loja-x", "7", 42)
    expect(screen.getByText(/Tiny retornou 400/)).toBeInTheDocument()
  })

  it("estado vazio com filtro", () => {
    renderTabela({ itens: [], temFiltros: true })
    expect(screen.getByText("Nenhum SKU com esse filtro.")).toBeInTheDocument()
  })

  // ---- "Tentar novamente" ----

  it("mostra 'Tentar novamente' só nas linhas com erro (e com variacao_id)", () => {
    renderTabela({
      itens: [
        linha({ log_id: 1, sku: "ERR-1", resultado: "erro", tiny_id: "" }),
        linha({ log_id: 2, sku: "OK-2", resultado: "criado" }),
        linha({ log_id: 3, sku: "BLK-3", resultado: "bloqueado" }),
        linha({ log_id: 4, sku: "SEM-VAR", resultado: "erro", variacao_id: null }),
      ],
    })
    const botoes = screen.getAllByRole("button", { name: /Tentar cadastrar o SKU/ })
    expect(botoes).toHaveLength(1)
    expect(
      screen.getByRole("button", { name: "Tentar cadastrar o SKU ERR-1 novamente" }),
    ).toBeInTheDocument()
  })

  it("clicar em 'Tentar novamente' chama a mutation com o variacao_id da linha", () => {
    renderTabela({ itens: [linha({ variacao_id: 77, sku: "ERR-77", resultado: "erro", tiny_id: "" })] })

    fireEvent.click(screen.getByRole("button", { name: "Tentar cadastrar o SKU ERR-77 novamente" }))

    expect(retentarMutate).toHaveBeenCalledWith(77, expect.anything())
    expect(push).not.toHaveBeenCalled()
    expect(hooks.useRetentarVariacaoExecucao).toHaveBeenCalledWith("loja-x", "7")
  })

  it("enquanto a tentativa está em voo o botão vira 'Tentando…' e fica desabilitado", () => {
    vi.mocked(hooks.useRetentarVariacaoExecucao).mockReturnValue({
      mutate: retentarMutate,
      isPending: true,
    } as never)
    renderTabela({ itens: [linha({ variacao_id: 5, sku: "ERR-5", resultado: "erro", tiny_id: "" })] })

    const botao = screen.getByRole("button", { name: "Tentar cadastrar o SKU ERR-5 novamente" })
    expect(botao).toBeDisabled()
    expect(screen.getByText("Tentando…")).toBeInTheDocument()
    fireEvent.click(botao)
    expect(retentarMutate).not.toHaveBeenCalled()
  })

  it("retryBloqueado (lote rodando) desabilita o 'Tentar novamente' individual", () => {
    renderTabela({
      itens: [linha({ variacao_id: 5, sku: "ERR-5", resultado: "erro", tiny_id: "" })],
      retryBloqueado: true,
    })
    expect(
      screen.getByRole("button", { name: "Tentar cadastrar o SKU ERR-5 novamente" }),
    ).toBeDisabled()
  })

  // ---- seleção para retentativa em lote ----

  function selecao(over: Partial<import("./execucao-produtos-tabela").SelecaoErros> = {}) {
    return {
      selecionados: new Set<number>(),
      selecaoTodos: false,
      onToggle: vi.fn(),
      onTogglePagina: vi.fn(),
      ...over,
    }
  }

  it("sem prop `selecao` não há checkboxes", () => {
    renderTabela({ itens: [linha({ resultado: "erro", variacao_id: 1, tiny_id: "" })] })
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
  })

  it("com `selecao`: checkbox só nas linhas de erro; o do cabeçalho marca a página", () => {
    const s = selecao()
    renderTabela({
      selecao: s,
      itens: [
        linha({ log_id: 1, variacao_id: 10, sku: "E-1", resultado: "erro", tiny_id: "" }),
        linha({ log_id: 2, variacao_id: 11, sku: "E-2", resultado: "erro", tiny_id: "" }),
        linha({ log_id: 3, variacao_id: 12, sku: "OK", resultado: "criado" }),
      ],
    })
    // 1 (cabeçalho) + 2 (linhas de erro) — a linha "criado" não tem checkbox
    expect(screen.getAllByRole("checkbox")).toHaveLength(3)

    fireEvent.click(screen.getByRole("checkbox", { name: "Selecionar todos os erros desta página" }))
    expect(s.onTogglePagina).toHaveBeenCalledWith([10, 11], true)

    fireEvent.click(screen.getByRole("checkbox", { name: "Selecionar o SKU E-1" }))
    expect(s.onToggle).toHaveBeenCalledWith(10)
  })

  it("com `selecaoTodos`: os checkboxes aparecem marcados e desabilitados", () => {
    renderTabela({
      selecao: selecao({ selecaoTodos: true }),
      itens: [linha({ variacao_id: 10, sku: "E-1", resultado: "erro", tiny_id: "" })],
    })
    const cb = screen.getByRole("checkbox", { name: "Selecionar o SKU E-1" })
    expect(cb).toBeDisabled()
    expect(cb).toBeChecked()
  })
})
