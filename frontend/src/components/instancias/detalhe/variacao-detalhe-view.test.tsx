import { readFileSync } from "node:fs"
import { join } from "node:path"
import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ApiError } from "@/lib/api/client"
import { VariacaoDetalheView } from "./variacao-detalhe-view"
import type { VariacaoDetalhe } from "@/lib/api/types"
import { ToastProvider } from "@/components/ui/toast"

vi.mock("@/lib/api/hooks", () => ({
  useVariacaoInstancia: vi.fn(),
  useAtualizarVariacaoFornecedor: vi.fn(),
  useAtualizarVariacaoTiny: vi.fn(),
  useStatusAtualizarVariacaoFornecedor: vi.fn(),
}))

const atualizarFornecedor = vi.fn()
const atualizarTiny = vi.fn()

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
    sku: "X134066",
    codigo_fornecedor: "X134066",
    sku_tiny: "18700-AZU",
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
    preco_custo_tiny_sincronizado: "19.90",
    dados_tiny_sincronizados_em: null,
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

function renderDetalhe() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider>
        <VariacaoDetalheView slug="loja-x" variacaoId="42" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe("VariacaoDetalheView", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(hooks.useAtualizarVariacaoFornecedor).mockReturnValue({ mutate: atualizarFornecedor, isPending: false } as never)
    vi.mocked(hooks.useAtualizarVariacaoTiny).mockReturnValue({ mutate: atualizarTiny, isPending: false } as never)
    vi.mocked(hooks.useStatusAtualizarVariacaoFornecedor).mockReturnValue({ data: undefined } as never)
  })

  it("renderiza cabeçalho, informações principais e link de voltar", () => {
    mock({ data: detalhe() })
    renderDetalhe()

    expect(screen.getByRole("heading", { name: "Caneca de porcelana" })).toBeInTheDocument()
    expect(screen.getAllByText("X134066").length).toBeGreaterThan(0)
    expect(screen.getAllByText("18700-AZU").length).toBeGreaterThan(0)
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
    renderDetalhe()

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
    renderDetalhe()

    const paragrafo = screen.getByText(longa)
    expect(paragrafo).toBeInTheDocument()
    expect(paragrafo.tagName).toBe("P")

    // A causa raiz do bug: neste projeto `globals.css` define tokens
    // `@theme` de espaçamento nomeados (--spacing-sm/2xl/…) e o Tailwind v4
    // resolve `max-w-<nome>` por esse namespace — `max-w-2xl` compila para
    // `max-width: 24px`, colapsando o bloco. O bloco da descrição precisa
    // usar um valor ARBITRÁRIO (`max-w-[Nrem]`), que é emitido literal.
    const container = paragrafo.parentElement!
    expect(container.className).toMatch(/\bmax-w-\[\d+(?:\.\d+)?rem\]/)
    expect(container.className).not.toMatch(
      /\bmax-w-(?:xs|sm|md|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl)\b/,
    )
  })

  it("NENHUM className do componente usa max-w-<nome> (quebrado neste projeto: vira 8–32px)", () => {
    // Proteção real contra a regressão: `max-w-sm/md/lg/xl/2xl/3xl/…` neste
    // projeto compilam para os valores de `--spacing-*` (8px … 32px), não
    // para larguras de container. Só valores arbitrários `max-w-[…]` são
    // seguros. Vale para QUALQUER elemento deste arquivo, não só a descrição.
    const fonte = readFileSync(
      join(process.cwd(), "src/components/instancias/detalhe/variacao-detalhe-view.tsx"),
      "utf8",
    )
    // tira comentários (que citam o bug de propósito) antes de varrer o código
    const codigo = fonte
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|[^:])\/\/.*$/gm, "$1")
    const ocorrencias = codigo.match(
      /\bmax-w-(?:xs|sm|md|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl)\b/g,
    )
    expect(ocorrencias).toBeNull()
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
    const { container } = renderDetalhe()

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
    renderDetalhe()
    expect(screen.getByText("garantia do produto")).toBeInTheDocument()
  })

  it("renderiza a galeria com miniaturas quando há múltiplas imagens", () => {
    mock({ data: detalhe() })
    renderDetalhe()
    expect(screen.getAllByRole("button", { name: /Ver imagem \d+ de 2/ })).toHaveLength(2)
  })

  it("usa o fallback de imagem quando não há imagens na variação nem no produto", () => {
    mock({ data: detalhe({ imagens: [], produto_imagens: [] }) })
    renderDetalhe()
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
    renderDetalhe()

    expect(screen.queryByText("Tiny ID")).not.toBeInTheDocument()
    expect(screen.queryByText("Especificações")).not.toBeInTheDocument()
    // NCM e variação/cor viram travessão
    expect(screen.getAllByText("—").length).toBeGreaterThan(0)
    // a seção "Dados técnicos" continua presente
    expect(screen.getByText("Dados técnicos")).toBeInTheDocument()
  })

  it("mostra o alerta de último erro quando existe", () => {
    mock({ data: detalhe({ status: "erro", status_rotulo: "Erro ao cadastrar", ultimo_erro: "SKU já existe no Tiny" }) })
    renderDetalhe()
    expect(screen.getByText("SKU já existe no Tiny")).toBeInTheDocument()
  })

  it("mostra 'Variação não encontrada' num 404", () => {
    mock({ isError: true, error: new ApiError(404, "Não encontrado.") })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ToastProvider>
          <VariacaoDetalheView slug="loja-x" variacaoId="999" />
        </ToastProvider>
      </QueryClientProvider>,
    )
    expect(screen.getByText("Variação não encontrada")).toBeInTheDocument()
  })

  it("mostra o estado de erro genérico com retry para falhas não-404", () => {
    mock({ isError: true, error: new ApiError(500, "Erro interno.") })
    renderDetalhe()
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument()
  })

  it("mostra skeletons enquanto carrega", () => {
    mock({ isLoading: true })
    const { container } = renderDetalhe()
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)
  })

  it("aciona cada atualização individual com a variação atual", () => {
    mock({ data: detalhe() })
    renderDetalhe()

    screen.getByRole("button", { name: "Atualizar do fornecedor" }).click()
    screen.getByRole("button", { name: "Atualizar no Tiny" }).click()

    expect(atualizarFornecedor).toHaveBeenCalledWith(42, expect.objectContaining({ onSuccess: expect.any(Function) }))
    expect(atualizarTiny).toHaveBeenCalledWith(42, expect.objectContaining({ onSuccess: expect.any(Function) }))
  })

  it("desabilita as duas ações e mostra loading durante uma atualização", () => {
    vi.mocked(hooks.useAtualizarVariacaoFornecedor).mockReturnValue({ mutate: atualizarFornecedor, isPending: true } as never)
    mock({ data: detalhe() })
    renderDetalhe()

    expect(screen.getByRole("button", { name: "Atualizando…" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Atualizar no Tiny" })).toBeDisabled()
  })

  it("mantém o botão em loading enquanto o status Celery está rodando", () => {
    vi.mocked(hooks.useStatusAtualizarVariacaoFornecedor).mockReturnValue({
      data: { id: 9, variacao: 42, fornecedor: "xbz", status: "rodando", erro: "" },
    } as never)
    mock({ data: detalhe() })
    renderDetalhe()

    expect(screen.getByRole("button", { name: "Atualizando…" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Atualizar no Tiny" })).toBeDisabled()
  })

  it("mantém todos os dados do produto durante o polling da operação", () => {
    vi.mocked(hooks.useStatusAtualizarVariacaoFornecedor).mockReturnValue({
      data: { id: 9, variacao: 42, fornecedor: "xbz", status: "rodando", erro: "" },
    } as never)
    mock({ data: detalhe() })
    renderDetalhe()

    expect(screen.getByRole("heading", { name: "Caneca de porcelana" })).toBeInTheDocument()
    expect(screen.getAllByText("X134066").length).toBeGreaterThan(0)
    expect(screen.getAllByText("18700-AZU").length).toBeGreaterThan(0)
    expect(screen.getByText("tiny-123")).toBeInTheDocument()
    expect(screen.getAllByText("R$ 19,90").length).toBeGreaterThan(0)
    expect(screen.getAllByRole("button", { name: /Ver imagem/ })).toHaveLength(2)
    expect(screen.getByRole("button", { name: "Atualizando…" })).toBeDisabled()
  })

  it("mantém os dados e mostra o erro real quando a operação termina com erro", async () => {
    vi.mocked(hooks.useStatusAtualizarVariacaoFornecedor).mockReturnValue({
      data: { id: 9, variacao: 42, fornecedor: "xbz", status: "erro", erro: "API XBZ indisponível" },
    } as never)
    atualizarFornecedor.mockImplementation((_id, opcoes) => opcoes.onSuccess({ id: 9 }))
    mock({ data: detalhe() })
    renderDetalhe()

    screen.getByRole("button", { name: "Atualizar do fornecedor" }).click()

    await waitFor(() => expect(screen.getByText("API XBZ indisponível")).toBeInTheDocument())
    expect(screen.getByRole("heading", { name: "Caneca de porcelana" })).toBeInTheDocument()
    expect(screen.getAllByText("X134066").length).toBeGreaterThan(0)
    expect(screen.getAllByText("18700-AZU").length).toBeGreaterThan(0)
    expect(screen.getAllByText("R$ 19,90").length).toBeGreaterThan(0)
  })

  it("exibe o erro devolvido pelo backend no toast", async () => {
    atualizarFornecedor.mockImplementation((_id, opcoes) => opcoes.onError(new ApiError(502, "Fornecedor indisponível")))
    mock({ data: detalhe() })
    renderDetalhe()

    screen.getByRole("button", { name: "Atualizar do fornecedor" }).click()

    await waitFor(() => expect(screen.getByText("Fornecedor indisponível")).toBeInTheDocument())
  })
})
