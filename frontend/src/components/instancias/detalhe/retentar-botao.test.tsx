import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ToastProvider } from "@/components/ui/toast"
import { RetentarBotao } from "./retentar-botao"
import type { ExecucaoProduto } from "@/lib/api/types"

function linha(over: Partial<ExecucaoProduto> = {}): ExecucaoProduto {
  return {
    log_id: 10,
    variacao_id: 42,
    sku: "MC511",
    codigo_fornecedor: "MC511",
    sku_tiny: "MC511",
    produto_nome: "Mochila",
    resultado: "erro",
    tiny_id: "",
    mensagem: "Falha ao sincronizar SKU MC511",
    detalhe_curto: "Tiny retornou 400: descricao obrigatória",
    imagens: null,
    criado_em: "2026-01-01T00:00:00Z",
    ...over,
  }
}

function montar(item: ExecucaoProduto) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const filtros = {}
  client.setQueryData(["instancias", "execucoes", "produtos", "loja-x", "7", filtros], {
    count: 1,
    results: [item],
  })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RetentarBotao slug="loja-x" execucaoId="7" linha={item} />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { client, filtros }
}

afterEach(() => vi.unstubAllGlobals())

describe("RetentarBotao", () => {
  it("não renderiza para linhas que não são erro", () => {
    montar(linha({ resultado: "criado", tiny_id: "5" }))
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("sucesso: POST, toast e cache inativo marcado para refetch sem substituir paginação", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            linha({ resultado: "criado", tiny_id: "99", detalhe_curto: "", mensagem: "SKU MC511 criado no Tiny" }),
          ),
          { status: 200 },
        ),
      ),
    )
    vi.stubGlobal("fetch", fetchMock)
    const { client, filtros } = montar(linha())

    fireEvent.click(screen.getByRole("button", { name: "Tentar cadastrar o SKU MC511 novamente" }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/backend/instancias/loja-x/execucoes/7/produtos/42/retentar/",
      expect.objectContaining({ method: "POST" }),
    )
    await screen.findByText("SKU MC511 cadastrado no Tiny.")
    await waitFor(() => {
      const cache = client.getQueryState([
        "instancias", "execucoes", "produtos", "loja-x", "7", filtros,
      ])
      expect(cache?.isInvalidated).toBe(true)
    })
  })

  it("falha de novo: toast com o erro REAL do backend, sem mascarar; linha mantida", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "Novo erro: campo origem inválido" }), { status: 422 }),
        ),
      ),
    )
    const { client, filtros } = montar(linha())

    fireEvent.click(screen.getByRole("button", { name: "Tentar cadastrar o SKU MC511 novamente" }))

    await screen.findByText("Novo erro: campo origem inválido")
    const cache = client.getQueryData([
      "instancias", "execucoes", "produtos", "loja-x", "7", filtros,
    ]) as { results: ExecucaoProduto[] }
    expect(cache.results[0].resultado).toBe("erro")
  })

  it("clique duplo: o 2º clique enquanto o POST está em voo é ignorado", async () => {
    let liberar!: (r: Response) => void
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => (liberar = resolve)))
    vi.stubGlobal("fetch", fetchMock)
    montar(linha())

    const botao = screen.getByRole("button", { name: "Tentar cadastrar o SKU MC511 novamente" })
    fireEvent.click(botao)
    await waitFor(() => expect(botao).toBeDisabled())
    fireEvent.click(botao)
    fireEvent.click(botao)

    liberar(new Response(JSON.stringify(linha({ resultado: "criado", tiny_id: "1" })), { status: 200 }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })
})
