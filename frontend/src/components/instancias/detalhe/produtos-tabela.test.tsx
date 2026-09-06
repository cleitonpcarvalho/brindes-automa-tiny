import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ProdutosTabela } from "./produtos-tabela"
import type { VariacaoEspelho } from "@/lib/api/types"

function variacao(overrides: Partial<VariacaoEspelho> = {}): VariacaoEspelho {
  return {
    id: 1,
    fornecedor: "xbz",
    produto_codigo_pai: "CANECA-01",
    produto_nome: "Caneca de porcelana",
    produto_descontinuado: false,
    sku: "CN-01-AZUL",
    nome: "Caneca azul 300ml",
    cor: "Azul",
    tamanho: "300ml",
    capacidade: "",
    preco: "19.90",
    estoque: 7,
    status: "cadastrado",
    status_rotulo: "Cadastrado no Tiny",
    tiny_id: "tiny-123",
    estoque_tiny_sincronizado: 7,
    ultimo_erro: "",
    cadastrado_em: null,
    atualizado_em: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

describe("ProdutosTabela", () => {
  it("mostra o estado vazio sem filtros", () => {
    render(
      <ProdutosTabela itens={[]} isLoading={false} isError={false} onRetry={vi.fn()} temFiltros={false} />,
    )
    expect(screen.getByText("Nenhum produto no espelho")).toBeInTheDocument()
    expect(screen.getByText(/depois da primeira sincronização/)).toBeInTheDocument()
  })

  it("mostra o estado vazio com filtros com mensagem diferente", () => {
    render(
      <ProdutosTabela itens={[]} isLoading={false} isError={false} onRetry={vi.fn()} temFiltros />,
    )
    expect(screen.getByText("Ajuste a busca ou os filtros.")).toBeInTheDocument()
  })

  it("mostra o erro com botão de tentar de novo", () => {
    const onRetry = vi.fn()
    render(
      <ProdutosTabela itens={[]} isLoading={false} isError onRetry={onRetry} temFiltros={false} />,
    )
    screen.getByRole("button", { name: "Tentar de novo" }).click()
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it("renderiza a linha com SKU, código-pai, variação, preço em BRL e situação", () => {
    render(
      <ProdutosTabela
        itens={[variacao()]}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
        temFiltros={false}
      />,
    )
    expect(screen.getByText("CN-01-AZUL")).toBeInTheDocument()
    expect(screen.getByText("CANECA-01")).toBeInTheDocument()
    expect(screen.getByText("Azul · 300ml")).toBeInTheDocument()
    expect(screen.getByText("R$ 19,90")).toBeInTheDocument()
    expect(screen.getByText("Cadastrado no Tiny")).toBeInTheDocument()
    expect(screen.getByText("XBZ")).toBeInTheDocument()
  })

  it("mostra travessão quando a variação não tem cor/tamanho/capacidade", () => {
    render(
      <ProdutosTabela
        itens={[variacao({ cor: "", tamanho: "", capacidade: "" })]}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
        temFiltros={false}
      />,
    )
    expect(screen.getByText("—")).toBeInTheDocument()
  })
})
