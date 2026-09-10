import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ApiError } from "@/lib/api/client"
import { ToastProvider } from "@/components/ui/toast"
import { ExecucaoDetalheView } from "./execucao-detalhe-view"
import type { ExecucaoDetalhe, PaginatedExecucaoProdutoList } from "@/lib/api/types"

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock("@/lib/api/hooks", () => ({
  useExecucaoDetalhe: vi.fn(),
  useExecucaoProdutos: vi.fn(),
  useExecucaoProdutoLogs: vi.fn(),
  useExecucaoLogsGerais: vi.fn(),
  useRetentarLote: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  usePararRetentarLote: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRetentarLoteProgresso: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useRetentarVariacaoExecucao: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

function renderView(execucaoId = "12", queryInicial = "") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider>
        <ExecucaoDetalheView slug="loja-x" execucaoId={execucaoId} queryInicial={queryInicial} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function resumo(over: Partial<ExecucaoDetalhe> = {}): ExecucaoDetalhe {
  return {
    id: 12,
    fornecedor: "asia",
    tipo: "cadastro_tiny",
    status: "pausado",
    estado: "pausado",
    iniciada_em: "2026-01-01T00:00:00Z",
    finalizada_em: null,
    duracao_segundos: 1800,
    total_lidos: 427,
    total_cadastrados: 421,
    total_erros: 6,
    total_ignorados: 0,
    contadores_registrados: { total_lidos: 1137, total_cadastrados: 421, total_erros: 6, total_ignorados: 710 },
    progresso: 0.3755,
    mensagem_erro: "",
    auditoria: {
      total: 427,
      cadastrados: 421,
      vinculados: 0,
      cadastrados_e_vinculados: 421,
      bloqueados: 0,
      erros: 6,
    },
    logs_gerais_total: 3,
    ...over,
  }
}

function produtos(over: Partial<PaginatedExecucaoProdutoList> = {}): PaginatedExecucaoProdutoList {
  return { count: 428, next: null, previous: null, results: [], ...over } as PaginatedExecucaoProdutoList
}

function mockResumo(estado: Record<string, unknown>) {
  vi.mocked(hooks.useExecucaoDetalhe).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...estado,
  } as never)
}

describe("ExecucaoDetalheView", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(hooks.useExecucaoProdutos).mockReturnValue({
      data: produtos(),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never)
    vi.mocked(hooks.useExecucaoLogsGerais).mockReturnValue({
      data: { results: [] },
      isLoading: false,
      isError: false,
    } as never)
    vi.mocked(hooks.useExecucaoProdutoLogs).mockReturnValue({
      data: { results: [] },
      isLoading: false,
      isError: false,
    } as never)
  })

  it("resumo e abas usam contadores conciliados; fila histórica aparece separada", () => {
    mockResumo({ data: resumo() })
    renderView()

    expect(screen.getByText("Pausado")).toBeInTheDocument()
    expect(screen.getByText("427")).toBeInTheDocument()
    expect(screen.getAllByText("421").length).toBeGreaterThan(0)
    expect(screen.getAllByText("6").length).toBeGreaterThan(0)
    expect(screen.getByText("Produtos com resultado")).toBeInTheDocument()
    expect(screen.getByText("Contadores registrados do fornecedor (última consolidação)")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "38")
  })

  it("execução concluída preserva a mesma semântica de bloqueados", () => {
    mockResumo({ data: resumo({ estado: "concluido", status: "sucesso" }) })
    renderView()
    expect(screen.getAllByText("Ignorados / bloqueados").length).toBeGreaterThan(0)
  })

  it("restaura filtro, busca e página vindos do retorno do produto", () => {
    mockResumo({ data: resumo() })
    renderView("10", "busca=18700-DOU&resultado=erros&page=3")
    expect(hooks.useExecucaoProdutos).toHaveBeenLastCalledWith("loja-x", "10", {
      busca: "18700-DOU", resultado: "erros", page: 3, pageSize: 25,
    })
    expect(screen.getByRole("textbox")).toHaveValue("18700-DOU")
  })

  it("badge segue o `estado` consolidado: retentativas zeraram os erros -> 'Concluído', sem 'Parcial'", () => {
    mockResumo({
      data: resumo({
        estado: "concluido",
        status: "sucesso",
        total_erros: 0,
        total_ignorados: 0,
        auditoria: {
          total: 1240,
          cadastrados: 1240,
          vinculados: 0,
          cadastrados_e_vinculados: 1240,
          bloqueados: 0,
          erros: 0,
        },
      }),
    })
    renderView()
    expect(screen.getByText("Concluído")).toBeInTheDocument()
    expect(screen.queryByText("Parcial / com erros")).not.toBeInTheDocument()
  })

  it("badge continua 'Parcial / com erros' enquanto o `estado` for parcial", () => {
    mockResumo({ data: resumo({ estado: "parcial", status: "parcial", total_erros: 3 }) })
    renderView()
    expect(screen.getByText("Parcial / com erros")).toBeInTheDocument()
  })

  it("filtros de resultado com contagem nos rótulos", () => {
    mockResumo({ data: resumo() })
    renderView()
    expect(screen.getByRole("button", { name: "Todos" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Erros/ })).toHaveTextContent("6")
    expect(screen.getByRole("button", { name: /Cadastrados/ })).toHaveTextContent("421")
  })

  it("mostra a seção 'Logs técnicos' com a contagem", () => {
    mockResumo({ data: resumo({ logs_gerais_total: 3 }) })
    renderView()
    expect(screen.getByText("Logs técnicos (3)")).toBeInTheDocument()
  })

  it("404 -> 'Execução não encontrada'", () => {
    mockResumo({ isError: true, error: new ApiError(404, "não encontrado") })
    renderView("999")
    expect(screen.getByText("Execução não encontrada")).toBeInTheDocument()
  })

  it("link de voltar aponta para a aba Execuções", () => {
    mockResumo({ data: resumo() })
    renderView()
    expect(screen.getByRole("link", { name: /Voltar para Execuções/ })).toHaveAttribute(
      "href",
      "/instancias/loja-x?tab=execucoes",
    )
  })

  it("execução de importação de espelho (não cadastro_tiny) usa o badge de status cru", () => {
    mockResumo({
      data: resumo({ tipo: "incremental", estado: "sucesso", status: "sucesso" }),
    })
    renderView()
    expect(screen.getByText("Sucesso")).toBeInTheDocument()
  })

  // ---- retentativa em lote ----

  it("a barra de lote só aparece no filtro 'Erros' e 'selecionar todos' dispara o lote", () => {
    const mutate = vi.fn()
    vi.mocked(hooks.useRetentarLote).mockReturnValue({ mutate, isPending: false } as never)
    mockResumo({ data: resumo() })
    renderView()

    // sem filtro: sem barra
    expect(screen.queryByText(/SKUs? com erro/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Erros/ }))
    expect(screen.getByText("6 SKUs com erro")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Selecionar todos os 6 erros da execução/ }))
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente selecionados (6)" }))

    expect(mutate).toHaveBeenCalledWith(
      { todos: true, busca: "" },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it("com o lote rodando: mostra o progresso e o botão Parar", () => {
    vi.mocked(hooks.useRetentarLoteProgresso).mockReturnValue({
      data: {
        id: 1, status: "rodando", selecao_todos: true, total: 6, processados: 2,
        sucessos: 2, erros: 0, ignorados: 0, criado_em: "x", finalizado_em: null,
      },
      isLoading: false,
      isError: false,
    } as never)
    mockResumo({ data: resumo() })
    renderView()
    fireEvent.click(screen.getByRole("button", { name: /Erros/ }))

    expect(screen.getByText("Retentativa em lote em andamento")).toBeInTheDocument()
    expect(screen.getByText(/2\/6/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Parar" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Tentar novamente selecionados/ })).not.toBeInTheDocument()
  })

  it("quando o lote conclui: toast de resumo e a barra de progresso some", async () => {
    const client = new QueryClient()
    vi.mocked(hooks.useRetentarLoteProgresso).mockReturnValue({
      data: {
        id: 1, status: "rodando", selecao_todos: true, total: 3, processados: 1,
        sucessos: 1, erros: 0, ignorados: 0, criado_em: "x", finalizado_em: null,
      },
      isLoading: false, isError: false,
    } as never)
    mockResumo({ data: resumo() })
    const tree = () => (
      <QueryClientProvider client={client}>
        <ToastProvider>
          <ExecucaoDetalheView slug="loja-x" execucaoId="12" />
        </ToastProvider>
      </QueryClientProvider>
    )
    const { rerender } = render(tree())
    fireEvent.click(screen.getByRole("button", { name: /Erros/ }))
    expect(screen.getByText("Retentativa em lote em andamento")).toBeInTheDocument()

    vi.mocked(hooks.useRetentarLoteProgresso).mockReturnValue({
      data: {
        id: 1, status: "concluido", selecao_todos: true, total: 3, processados: 3,
        sucessos: 3, erros: 0, ignorados: 0, criado_em: "x", finalizado_em: "y",
      },
      isLoading: false, isError: false,
    } as never)
    rerender(tree())

    await waitFor(() =>
      expect(screen.getByText(/Retentativa em lote concluída: 3 cadastrado/)).toBeInTheDocument(),
    )
    expect(screen.queryByText("Retentativa em lote em andamento")).not.toBeInTheDocument()
  })
})
