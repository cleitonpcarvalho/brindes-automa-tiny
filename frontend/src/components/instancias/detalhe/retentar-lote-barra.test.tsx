import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RetentarLoteBarra } from "./retentar-lote-barra"
import type { RetentativaLote } from "@/lib/api/types"

function lote(over: Partial<RetentativaLote> = {}): RetentativaLote {
  return {
    id: 1,
    status: "rodando",
    selecao_todos: false,
    total: 10,
    processados: 4,
    sucessos: 3,
    erros: 1,
    ignorados: 0,
    criado_em: "2026-01-01T00:00:00Z",
    finalizado_em: null,
    ...over,
  }
}

function renderBarra(props: Partial<Parameters<typeof RetentarLoteBarra>[0]> = {}) {
  const base = {
    qtdErrosTotal: 8,
    qtdSelecionada: 0,
    selecaoTodos: false,
    progresso: null,
    disparando: false,
    onSelecionarTodos: vi.fn(),
    onLimpar: vi.fn(),
    onDisparar: vi.fn(),
  }
  const p = { ...base, ...props }
  render(<RetentarLoteBarra {...p} />)
  return p
}

describe("RetentarLoteBarra", () => {
  it("sem seleção: mostra o total de erros e o 'Selecionar todos'", () => {
    renderBarra({ qtdErrosTotal: 8 })
    expect(screen.getByText("8 SKUs com erro")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Selecionar todos os 8 erros da execução/ }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Tentar novamente selecionados/ })).not.toBeInTheDocument()
  })

  it("com N selecionados: botão 'Tentar novamente selecionados (N)' dispara", () => {
    const p = renderBarra({ qtdSelecionada: 3 })
    const botao = screen.getByRole("button", { name: "Tentar novamente selecionados (3)" })
    fireEvent.click(botao)
    expect(p.onDisparar).toHaveBeenCalledOnce()
  })

  it("selecaoTodos: conta todos os erros e some o 'Selecionar todos'", () => {
    renderBarra({ selecaoTodos: true, qtdErrosTotal: 8, qtdSelecionada: 0 })
    expect(screen.getByText("Todos os 8 erros selecionados")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Tentar novamente selecionados (8)" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Selecionar todos/ })).not.toBeInTheDocument()
  })

  it("'Selecionar todos' chama o callback", () => {
    const p = renderBarra({ qtdErrosTotal: 8, qtdSelecionada: 2 })
    fireEvent.click(screen.getByRole("button", { name: /Selecionar todos os 8 erros/ }))
    expect(p.onSelecionarTodos).toHaveBeenCalledOnce()
  })

  it("job rodando: mostra progresso processados/total e barra, sem botões de ação", () => {
    renderBarra({ progresso: lote({ status: "rodando", total: 10, processados: 4, sucessos: 3, erros: 1 }) })
    expect(screen.getByText("Retentativa em lote em andamento")).toBeInTheDocument()
    expect(screen.getByText(/4\/10/)).toBeInTheDocument()
    expect(screen.getByText(/3 ok/)).toBeInTheDocument()
    expect(screen.getByText(/1 erro/)).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40")
    expect(screen.queryByRole("button", { name: /Tentar novamente/ })).not.toBeInTheDocument()
  })

  it("job concluído não é mostrado como progresso (barra de ação normal)", () => {
    renderBarra({ progresso: lote({ status: "concluido" }), qtdErrosTotal: 2 })
    expect(screen.queryByText("Retentativa em lote em andamento")).not.toBeInTheDocument()
    expect(screen.getByText("2 SKUs com erro")).toBeInTheDocument()
  })
})
