import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ExecucoesHistoricoTabela } from "./execucoes-historico-tabela"
import type { Execucao } from "@/lib/api/types"

function execucao(overrides: Partial<Execucao> = {}): Execucao {
  return {
    id: 1,
    fornecedor: "xbz",
    tipo: "incremental",
    status: "sucesso",
    iniciada_em: new Date(Date.now() - 40 * 60_000).toISOString(),
    finalizada_em: new Date().toISOString(),
    duracao_segundos: 48,
    total_lidos: 1156,
    total_novos: 4,
    total_atualizados: 12,
    total_cadastrados: 3,
    total_ignorados: 1,
    total_erros: 0,
    mensagem_erro: "",
    total_logs: 5,
    ...overrides,
  }
}

const noop = () => {}

describe("ExecucoesHistoricoTabela", () => {
  it("mostra skeletons durante o carregamento", () => {
    const { container } = render(
      <ExecucoesHistoricoTabela
        itens={[]}
        isLoading
        isError={false}
        onRetry={noop}
        slug="loja-x"
        temFiltros={false}
      />,
    )
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)
  })

  it("mostra estado vazio sem filtros", () => {
    render(
      <ExecucoesHistoricoTabela
        itens={[]}
        isLoading={false}
        isError={false}
        onRetry={noop}
        slug="loja-x"
        temFiltros={false}
      />,
    )
    expect(screen.getByText("Nenhuma execução")).toBeInTheDocument()
    expect(screen.getByText(/a cada sincronização/)).toBeInTheDocument()
  })

  it("mostra mensagem específica de filtros no estado vazio", () => {
    render(
      <ExecucoesHistoricoTabela
        itens={[]}
        isLoading={false}
        isError={false}
        onRetry={noop}
        slug="loja-x"
        temFiltros
      />,
    )
    expect(screen.getByText("Ajuste os filtros.")).toBeInTheDocument()
  })

  it("mostra erro com botão de tentar de novo", () => {
    const onRetry = vi.fn()
    render(
      <ExecucoesHistoricoTabela
        itens={[]}
        isLoading={false}
        isError
        onRetry={onRetry}
        slug="loja-x"
        temFiltros={false}
      />,
    )
    screen.getByRole("button", { name: "Tentar de novo" }).click()
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it("renderiza a linha com fornecedor, tipo, badge de status e resultado", () => {
    render(
      <ExecucoesHistoricoTabela
        itens={[execucao({ status: "sucesso" })]}
        isLoading={false}
        isError={false}
        onRetry={noop}
        slug="loja-x"
        temFiltros={false}
      />,
    )
    expect(screen.getByText("XBZ")).toBeInTheDocument()
    expect(screen.getByText("Incremental")).toBeInTheDocument()
    expect(screen.getByText("Sucesso")).toBeInTheDocument()
    expect(screen.getByText("1.156 lidos · 4 novos · 12 atualizados · 0 erros")).toBeInTheDocument()
  })

  it("mostra a mensagem de erro no resultado quando a execução falhou", () => {
    render(
      <ExecucoesHistoricoTabela
        itens={[execucao({ status: "falha", mensagem_erro: "HTTP 401 Unauthorized" })]}
        isLoading={false}
        isError={false}
        onRetry={noop}
        slug="loja-x"
        temFiltros={false}
      />,
    )
    expect(screen.getByText("Falha")).toBeInTheDocument()
    expect(screen.getByText("HTTP 401 Unauthorized")).toBeInTheDocument()
  })

  it("'Ver' leva para a página de detalhe da execução", () => {
    const itens = [execucao({ id: 7, total_logs: 5 }), execucao({ id: 9, total_logs: 0 })]
    render(
      <ExecucoesHistoricoTabela
        itens={itens}
        isLoading={false}
        isError={false}
        onRetry={noop}
        slug="loja-x"
        temFiltros={false}
      />,
    )
    const link = screen.getByRole("link", { name: "Ver (5)" })
    expect(link).toHaveAttribute("href", "/instancias/loja-x/execucoes/7")
    // sempre navegável, mesmo sem logs — a tela mostra o resumo
    expect(screen.getByRole("link", { name: "Ver" })).toHaveAttribute(
      "href",
      "/instancias/loja-x/execucoes/9",
    )
  })
})
