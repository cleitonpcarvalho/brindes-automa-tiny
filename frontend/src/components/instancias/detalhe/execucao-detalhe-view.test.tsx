import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ApiError } from "@/lib/api/client"
import { ExecucaoDetalheView } from "./execucao-detalhe-view"
import type { ExecucaoDetalhe, PaginatedExecucaoProdutoList } from "@/lib/api/types"

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock("@/lib/api/hooks", () => ({
  useExecucaoDetalhe: vi.fn(),
  useExecucaoProdutos: vi.fn(),
  useExecucaoProdutoLogs: vi.fn(),
  useExecucaoLogsGerais: vi.fn(),
}))

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
    total_lidos: 1137,
    total_cadastrados: 421,
    total_erros: 6,
    total_ignorados: 710,
    progresso: 0.3755,
    mensagem_erro: "",
    auditoria: {
      total: 428,
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

  it("resumo: fornecedor, estado, fila, cadastrados, erros, 'a fazer' e barra", () => {
    mockResumo({ data: resumo() })
    render(<ExecucaoDetalheView slug="loja-x" execucaoId="12" />)

    expect(screen.getByText("Pausado")).toBeInTheDocument()
    expect(screen.getByText("1.137")).toBeInTheDocument() // fila
    expect(screen.getAllByText("421").length).toBeGreaterThan(0)
    expect(screen.getAllByText("6").length).toBeGreaterThan(0)
    expect(screen.getByText("a fazer")).toBeInTheDocument() // pausado -> "a fazer"
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "38")
  })

  it("execução concluída rotula o 3º número como 'não cadastrados'", () => {
    mockResumo({ data: resumo({ estado: "concluido", status: "sucesso" }) })
    render(<ExecucaoDetalheView slug="loja-x" execucaoId="12" />)
    expect(screen.getByText("não cadastrados")).toBeInTheDocument()
  })

  it("filtros de resultado com contagem nos rótulos", () => {
    mockResumo({ data: resumo() })
    render(<ExecucaoDetalheView slug="loja-x" execucaoId="12" />)
    expect(screen.getByRole("button", { name: "Todos" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Erros/ })).toHaveTextContent("6")
    expect(screen.getByRole("button", { name: /Cadastrados/ })).toHaveTextContent("421")
  })

  it("mostra a seção 'Logs técnicos' com a contagem", () => {
    mockResumo({ data: resumo({ logs_gerais_total: 3 }) })
    render(<ExecucaoDetalheView slug="loja-x" execucaoId="12" />)
    expect(screen.getByText("Logs técnicos (3)")).toBeInTheDocument()
  })

  it("404 -> 'Execução não encontrada'", () => {
    mockResumo({ isError: true, error: new ApiError(404, "não encontrado") })
    render(<ExecucaoDetalheView slug="loja-x" execucaoId="999" />)
    expect(screen.getByText("Execução não encontrada")).toBeInTheDocument()
  })

  it("link de voltar aponta para a aba Execuções", () => {
    mockResumo({ data: resumo() })
    render(<ExecucaoDetalheView slug="loja-x" execucaoId="12" />)
    expect(screen.getByRole("link", { name: /Voltar para Execuções/ })).toHaveAttribute(
      "href",
      "/instancias/loja-x?tab=execucoes",
    )
  })

  it("execução de importação de espelho (não cadastro_tiny) usa o badge de status cru", () => {
    mockResumo({
      data: resumo({ tipo: "incremental", estado: "sucesso", status: "sucesso" }),
    })
    render(<ExecucaoDetalheView slug="loja-x" execucaoId="12" />)
    expect(screen.getByText("Sucesso")).toBeInTheDocument()
  })
})
