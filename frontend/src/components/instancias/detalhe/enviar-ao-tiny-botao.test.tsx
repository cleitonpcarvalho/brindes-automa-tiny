import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ToastProvider } from "@/components/ui/toast"
import { EnviarAoTinyBotao } from "./enviar-ao-tiny-botao"
import type { VariacaoEspelho } from "@/lib/api/types"

function variacao(overrides: Partial<VariacaoEspelho> = {}): VariacaoEspelho {
  return {
    id: 7,
    fornecedor: "asia",
    produto_codigo_pai: "BL026",
    produto_nome: "Mini caderno",
    produto_descontinuado: false,
    sku: "BL026-BG",
    nome: "Mini caderno bege",
    cor: "Bege",
    tamanho: "",
    capacidade: "",
    preco: "3.60",
    estoque: 10,
    status: "pendente",
    status_rotulo: "Pendente",
    tiny_id: null,
    estoque_tiny_sincronizado: null,
    ultimo_erro: "",
    cadastrado_em: null,
    atualizado_em: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

function montar(item: VariacaoEspelho) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  client.setQueryData(["instancias", "produtos", "loja-x", {}], { count: 1, results: [item] })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <EnviarAoTinyBotao slug="loja-x" variacao={item} />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return client
}

afterEach(() => vi.unstubAllGlobals())

describe("EnviarAoTinyBotao", () => {
  it("não renderiza nada quando a variação não está pendente", () => {
    montar(variacao({ status: "cadastrado" }))
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("sucesso: POST no endpoint certo, toast e linha atualizada para 'Cadastrado' no cache", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ ...variacao(), status: "cadastrado", status_rotulo: "Cadastrado no Tiny", tiny_id: "55" }),
          { status: 200 },
        ),
      ),
    )
    vi.stubGlobal("fetch", fetchMock)
    const client = montar(variacao())

    fireEvent.click(screen.getByRole("button", { name: "Enviar o SKU BL026-BG ao Tiny" }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/backend/instancias/loja-x/produtos/7/cadastro-tiny/",
      expect.objectContaining({ method: "POST" }),
    )

    await screen.findByText("SKU BL026-BG cadastrado no Tiny.")
    await waitFor(() => {
      const cache = client.getQueryData(["instancias", "produtos", "loja-x", {}]) as {
        results: VariacaoEspelho[]
      }
      expect(cache.results[0].status).toBe("cadastrado")
      expect(cache.results[0].tiny_id).toBe("55")
    })
  })

  it("erro: mostra a mensagem do backend SEM mascarar e mantém a linha", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "estoque <= 0 (estoque=0) — aguarda reposição" }), {
            status: 422,
          }),
        ),
      ),
    )
    const client = montar(variacao())

    fireEvent.click(screen.getByRole("button", { name: "Enviar o SKU BL026-BG ao Tiny" }))

    await screen.findByText("estoque <= 0 (estoque=0) — aguarda reposição")
    const cache = client.getQueryData(["instancias", "produtos", "loja-x", {}]) as {
      results: VariacaoEspelho[]
    }
    expect(cache.results[0].status).toBe("pendente") // linha inalterada
  })

  it("protege contra clique duplo: o 2º clique enquanto o POST está em voo é ignorado", async () => {
    let liberar!: (r: Response) => void
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => (liberar = resolve)))
    vi.stubGlobal("fetch", fetchMock)
    montar(variacao())

    const botao = screen.getByRole("button", { name: "Enviar o SKU BL026-BG ao Tiny" })
    fireEvent.click(botao)
    await waitFor(() => expect(botao).toBeDisabled())
    expect(screen.getByText("Enviando…")).toBeInTheDocument()

    fireEvent.click(botao) // 2º clique — botão desabilitado + guarda isPending
    fireEvent.click(botao)

    liberar(new Response(JSON.stringify(variacao({ status: "cadastrado" })), { status: 200 }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })
})
