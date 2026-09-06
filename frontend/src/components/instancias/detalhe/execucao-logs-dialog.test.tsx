import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ExecucaoLogsDialog } from "./execucao-logs-dialog"
import type { Execucao, LogItem } from "@/lib/api/types"

vi.mock("@/lib/api/hooks", () => ({
  useExecucaoLogs: vi.fn(),
}))

function execucao(overrides: Partial<Execucao> = {}): Execucao {
  return {
    id: 7,
    fornecedor: "spot",
    tipo: "carga_inicial",
    status: "parcial",
    iniciada_em: new Date(Date.now() - 60_000).toISOString(),
    finalizada_em: new Date().toISOString(),
    duracao_segundos: 12,
    total_lidos: 10,
    total_novos: 2,
    total_atualizados: 1,
    total_cadastrados: 2,
    total_ignorados: 1,
    total_erros: 1,
    mensagem_erro: "1 item falhou",
    total_logs: 2,
    ...overrides,
  }
}

function log(overrides: Partial<LogItem> = {}): LogItem {
  return {
    id: 1,
    nivel: "info",
    mensagem: "Sincronização iniciada",
    detalhe: {},
    criado_em: new Date().toISOString(),
    variacao_sku: null,
    ...overrides,
  }
}

function mockLogs(retorno: Partial<ReturnType<typeof hooks.useExecucaoLogs>>) {
  vi.mocked(hooks.useExecucaoLogs).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    ...retorno,
  } as never)
}

describe("ExecucaoLogsDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("não renderiza conteúdo quando não há execução selecionada", () => {
    mockLogs({})
    render(<ExecucaoLogsDialog slug="loja-x" execucao={null} onOpenChange={() => {}} />)
    expect(screen.queryByText(/Execução ·/)).not.toBeInTheDocument()
  })

  it("mostra cabeçalho, contadores, mensagem de erro e as linhas de log", () => {
    mockLogs({
      data: { count: 2, next: null, previous: null, results: [log({ id: 1, mensagem: "linha um" }), log({ id: 2, nivel: "erro", mensagem: "linha dois", variacao_sku: "SKU-9" })] },
    })
    render(<ExecucaoLogsDialog slug="loja-x" execucao={execucao()} onOpenChange={() => {}} />)

    expect(screen.getByText("Execução · Spot Gifts")).toBeInTheDocument()
    expect(screen.getByText("Parcial")).toBeInTheDocument()
    expect(screen.getByText("1 item falhou")).toBeInTheDocument()
    expect(screen.getByText("Cadastrados")).toBeInTheDocument()
    expect(screen.getByText("linha um")).toBeInTheDocument()
    expect(screen.getByText("linha dois")).toBeInTheDocument()
    expect(screen.getByText("SKU-9")).toBeInTheDocument()
  })

  it("mostra estado vazio quando a execução não tem logs", () => {
    mockLogs({ data: { count: 0, next: null, previous: null, results: [] } })
    render(<ExecucaoLogsDialog slug="loja-x" execucao={execucao({ total_logs: 0 })} onOpenChange={() => {}} />)
    expect(screen.getByText("Esta execução não registrou logs.")).toBeInTheDocument()
  })

  it("mostra erro com botão de tentar de novo", () => {
    const refetch = vi.fn()
    mockLogs({ isError: true, refetch })
    render(<ExecucaoLogsDialog slug="loja-x" execucao={execucao()} onOpenChange={() => {}} />)
    screen.getByRole("button", { name: "Tentar de novo" }).click()
    expect(refetch).toHaveBeenCalledOnce()
  })
})
