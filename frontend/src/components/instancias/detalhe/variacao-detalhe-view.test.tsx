import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ApiError } from "@/lib/api/client"
import { VariacaoDetalheView } from "./variacao-detalhe-view"
import type { VariacaoDetalhe } from "@/lib/api/types"

vi.mock("@/lib/api/hooks", () => ({ useVariacaoInstancia: vi.fn() }))

function detalhe(overrides: Partial<VariacaoDetalhe> = {}): VariacaoDetalhe {
  return {
    id: 42,
    fornecedor: "xbz",
    fornecedor_rotulo: "XBZ",
    produto_id: 7,
    produto_codigo_pai: "CANECA-01",
    produto_nome: "Caneca de porcelana",
    produto_descricao: "Caneca de porcelana 300ml.",
    produto_categorias: ["Canecas", "Cozinha"],
    produto_imagens: [],
    produto_atributos: {},
    produto_descontinuado: false,
    produto_atualizado_em_fornecedor: null,
    sku: "CN-01-AZUL",
    nome: "Caneca azul 300ml",
    ncm: "69120000",
    preco: "19.90",
    estoque: 7,
    cor: "Azul",
    tamanho: "300ml",
    capacidade: "",
    largura: 8,
    altura: 10.5,
    comprimento: null,
    diametro: null,
    peso_liquido: null,
    peso_bruto: 0.42,
    imagens: ["https://cdn.exemplo.com/azul-1.jpg", "https://cdn.exemplo.com/azul-2.jpg"],
    atributos: { material: "porcelana", taric: "6912.00.00" },
    status: "cadastrado",
    status_rotulo: "Cadastrado no Tiny",
    tiny_id: "tiny-123",
    ultimo_erro: "",
    cadastrado_em: "2026-02-01T12:00:00Z",
    criado_em: "2026-01-01T09:00:00Z",
    atualizado_em: "2026-02-10T09:00:00Z",
    estoque_tiny_sincronizado: 7,
    preco_tiny_sincronizado: "19.90",
    imagens_tiny_sincronizadas: ["https://cdn.exemplo.com/azul-1.jpg"],
    hash_conteudo: "abc123",
    ...overrides,
  }
}

function mock(estado: Record<string, unknown>) {
  vi.mocked(hooks.useVariacaoInstancia).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...estado,
  } as never)
}

describe("VariacaoDetalheView", () => {
  beforeEach(() => vi.clearAllMocks())

  it("renderiza cabeçalho, informações principais e link de voltar", () => {
    mock({ data: detalhe() })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)

    expect(screen.getByRole("heading", { name: "Caneca de porcelana" })).toBeInTheDocument()
    expect(screen.getAllByText("CN-01-AZUL").length).toBeGreaterThan(0)
    expect(screen.getAllByText("XBZ").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Cadastrado no Tiny").length).toBeGreaterThan(0)
    expect(screen.getByText("69120000")).toBeInTheDocument()
    expect(screen.getAllByText("R$ 19,90").length).toBeGreaterThan(0)
    expect(screen.getByText("Azul · 300ml")).toBeInTheDocument()
    expect(screen.getByText("tiny-123")).toBeInTheDocument()

    const voltar = screen.getByRole("link", { name: /Voltar para Produtos/ })
    expect(voltar).toHaveAttribute("href", "/instancias/loja-x?tab=produtos")
  })

  it("mostra as especificações (dimensões, peso, categorias, atributos)", () => {
    mock({ data: detalhe() })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)

    expect(screen.getByText("Especificações")).toBeInTheDocument()
    expect(screen.getByText("Largura 8 cm")).toBeInTheDocument()
    expect(screen.getByText("Bruto 0,42 kg")).toBeInTheDocument()
    expect(screen.getByText("Canecas")).toBeInTheDocument()
    expect(screen.getByText("material")).toBeInTheDocument()
    expect(screen.getByText("porcelana")).toBeInTheDocument()
  })

  it("renderiza uma descrição longa por extenso, num bloco de largura de leitura", () => {
    const longa =
      "Mochila para notebook de 15,6 polegadas em poliéster 600D com dois compartimentos, " +
      "divisória almofadada, interior forrado e alça de transporte reforçada para uso diário."
    mock({ data: detalhe({ produto_descricao: longa }) })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)

    const paragrafo = screen.getByText(longa)
    expect(paragrafo).toBeInTheDocument()
    expect(paragrafo.tagName).toBe("P")
    // o texto vive num bloco com teto de largura, não espremido pelo cabeçalho
    expect(paragrafo.closest("div")).toHaveClass("max-w-2xl")
  })

  it("apresenta atributos estruturados da Asia (objeto com value) de forma legível, sem JSON", () => {
    mock({
      data: detalhe({
        atributos: {
          cor: { name: "cinza", value: "Cinza", hexadecimal: "#7f7f7f" },
          "volume-litros": { name: "29l", value: "29L" },
        },
        produto_atributos: { "dimensao-produto": "39x42x18cm (AxLxP)" },
      }),
    })
    const { container } = render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)

    expect(screen.getByText("Cinza")).toBeInTheDocument()
    expect(screen.getByText("29L")).toBeInTheDocument()
    expect(screen.getByText("volume litros")).toBeInTheDocument()
    expect(screen.getByText("39x42x18cm (AxLxP)")).toBeInTheDocument()
    expect(container.textContent).not.toContain("[object Object]")
    expect(container.textContent).not.toContain('{"name"')
    expect(container.textContent).not.toContain("hexadecimal")
  })

  it("mantém um atributo de valor vazio visível como travessão (não some da lista)", () => {
    mock({ data: detalhe({ atributos: { garantia_do_produto: "" }, produto_atributos: {} }) })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)
    expect(screen.getByText("garantia do produto")).toBeInTheDocument()
  })

  it("renderiza a galeria com miniaturas quando há múltiplas imagens", () => {
    mock({ data: detalhe() })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)
    expect(screen.getAllByRole("button", { name: /Ver imagem \d+ de 2/ })).toHaveLength(2)
  })

  it("usa o fallback de imagem quando não há imagens na variação nem no produto", () => {
    mock({ data: detalhe({ imagens: [], produto_imagens: [] }) })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)
    expect(screen.getByText("Sem imagem no espelho")).toBeInTheDocument()
  })

  it("adapta-se a campos opcionais ausentes: sem Tiny ID, sem Especificações, travessões", () => {
    mock({
      data: detalhe({
        tiny_id: null,
        ncm: "",
        cor: "",
        tamanho: "",
        capacidade: "",
        largura: null,
        altura: null,
        comprimento: null,
        diametro: null,
        peso_liquido: null,
        peso_bruto: null,
        atributos: {},
        produto_atributos: {},
        produto_categorias: [],
        produto_descricao: "",
        status: "pendente",
        status_rotulo: "Pendente",
      }),
    })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)

    expect(screen.queryByText("Tiny ID")).not.toBeInTheDocument()
    expect(screen.queryByText("Especificações")).not.toBeInTheDocument()
    // NCM e variação/cor viram travessão
    expect(screen.getAllByText("—").length).toBeGreaterThan(0)
    // a seção "Dados técnicos" continua presente
    expect(screen.getByText("Dados técnicos")).toBeInTheDocument()
  })

  it("mostra o alerta de último erro quando existe", () => {
    mock({ data: detalhe({ status: "erro", status_rotulo: "Erro ao cadastrar", ultimo_erro: "SKU já existe no Tiny" }) })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)
    expect(screen.getByText("SKU já existe no Tiny")).toBeInTheDocument()
  })

  it("mostra 'Variação não encontrada' num 404", () => {
    mock({ isError: true, error: new ApiError(404, "Não encontrado.") })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="999" />)
    expect(screen.getByText("Variação não encontrada")).toBeInTheDocument()
  })

  it("mostra o estado de erro genérico com retry para falhas não-404", () => {
    mock({ isError: true, error: new ApiError(500, "Erro interno.") })
    render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument()
  })

  it("mostra skeletons enquanto carrega", () => {
    mock({ isLoading: true })
    const { container } = render(<VariacaoDetalheView slug="loja-x" variacaoId="42" />)
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)
  })
})
