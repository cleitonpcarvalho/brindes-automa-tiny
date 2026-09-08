import type { ComponentProps } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ToastProvider } from "@/components/ui/toast"
import { ProdutosTabela } from "./produtos-tabela"
import type { VariacaoEspelho } from "@/lib/api/types"

const push = vi.fn()
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}))

// A ação "Enviar ao Tiny" tem teste próprio (enviar-ao-tiny-botao.test.tsx);
// aqui só interessa que a tabela a renderiza para linhas `pendente`.
const mutate = vi.fn()
vi.mock("@/lib/api/hooks", () => ({
  useCadastrarVariacaoTiny: () => ({ mutate, isPending: false }),
}))

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

function renderTabela(props: Partial<ComponentProps<typeof ProdutosTabela>> = {}) {
  return render(
    <ToastProvider>
      <ProdutosTabela
        slug="loja-x"
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

describe("ProdutosTabela", () => {
  it("mostra o estado vazio sem filtros", () => {
    renderTabela()
    expect(screen.getByText("Nenhum produto no espelho")).toBeInTheDocument()
    expect(screen.getByText(/depois da primeira sincronização/)).toBeInTheDocument()
  })

  it("mostra o estado vazio com filtros com mensagem diferente", () => {
    renderTabela({ temFiltros: true })
    expect(screen.getByText("Ajuste a busca ou os filtros.")).toBeInTheDocument()
  })

  it("mostra o erro com botão de tentar de novo", () => {
    const onRetry = vi.fn()
    renderTabela({ isError: true, onRetry })
    screen.getByRole("button", { name: "Tentar de novo" }).click()
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it("renderiza a linha com SKU, código-pai, variação, preço em BRL e situação", () => {
    renderTabela({ itens: [variacao()] })
    expect(screen.getByText("CN-01-AZUL")).toBeInTheDocument()
    expect(screen.getByText("CANECA-01")).toBeInTheDocument()
    expect(screen.getByText("Azul · 300ml")).toBeInTheDocument()
    expect(screen.getByText("R$ 19,90")).toBeInTheDocument()
    expect(screen.getByText("Cadastrado no Tiny")).toBeInTheDocument()
    expect(screen.getByText("XBZ")).toBeInTheDocument()
  })

  it("mostra travessão quando a variação não tem cor/tamanho/capacidade", () => {
    renderTabela({ itens: [variacao({ cor: "", tamanho: "", capacidade: "" })] })
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("a linha é clicável e leva para o detalhe da variação na mesma instância", () => {
    push.mockClear()
    renderTabela({ itens: [variacao({ id: 42 })] })

    const linha = screen.getByRole("link", { name: "Ver detalhes de CN-01-AZUL" })
    expect(linha).toHaveClass("cursor-pointer")

    fireEvent.click(linha)
    expect(push).toHaveBeenCalledWith("/instancias/loja-x/produtos/42")

    push.mockClear()
    fireEvent.keyDown(linha, { key: "Enter" })
    expect(push).toHaveBeenCalledWith("/instancias/loja-x/produtos/42")
  })

  it("mostra 'Enviar ao Tiny' só nas linhas pendentes", () => {
    renderTabela({
      itens: [
        variacao({ id: 1, sku: "PEND-1", status: "pendente", status_rotulo: "Pendente" }),
        variacao({ id: 2, sku: "FEITO-2", status: "cadastrado" }),
        variacao({ id: 3, sku: "AGU-3", status: "aguardando" }),
      ],
    })
    const botoes = screen.getAllByRole("button", { name: /Enviar o SKU/ })
    expect(botoes).toHaveLength(1)
    expect(screen.getByRole("button", { name: "Enviar o SKU PEND-1 ao Tiny" })).toBeInTheDocument()
  })

  it("clicar em 'Enviar ao Tiny' dispara a mutation e NÃO navega para o detalhe", () => {
    push.mockClear()
    mutate.mockClear()
    renderTabela({
      itens: [variacao({ id: 9, sku: "PEND-9", status: "pendente", status_rotulo: "Pendente" })],
    })

    fireEvent.click(screen.getByRole("button", { name: "Enviar o SKU PEND-9 ao Tiny" }))

    expect(mutate).toHaveBeenCalledWith(9, expect.anything())
    expect(push).not.toHaveBeenCalled()
  })
})
