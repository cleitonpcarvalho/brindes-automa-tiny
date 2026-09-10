import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { apiClient, ApiError } from "./client"
import { useAtualizarVariacaoTiny, useExecucaoDetalhe, useExecucaoProdutos, useRetentarVariacaoExecucao, useVariacaoInstancia } from "./hooks"

afterEach(() => vi.restoreAllMocks())

describe("conciliação de cache Tiny com hooks e QueryClient reais", () => {
  it.each(["atualizar", "retry"])("%s refaz detalhe, contadores e páginas filtradas sem misturar formatos", async (fluxo) => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    const slug = "ekk-brindes"
    const produto = { id: 4996, sku: "X134074", sku_tiny: "18700-DOU", produto_nome: "Caneca", status: "erro", tiny_id: null }
    const produtoAtual = { ...produto, status: "cadastrado", tiny_id: "924385783" }
    const linha = { variacao_id: 4996, resultado: "vinculado", tiny_id: "924385783" }
    const chaveProduto = ["instancias", "produtos", "detalhe", slug, "4996"]
    const chaveOutraExecucao = ["instancias", "execucoes", "detalhe", slug, "9"]
    const chaveOutraInstancia = ["instancias", "execucoes", "detalhe", "outra", "10"]
    client.setQueryData(chaveProduto, produto)
    client.setQueryData(chaveOutraExecucao, { total_erros: 1 })
    client.setQueryData(chaveOutraInstancia, { total_erros: 1 })
    let concluido = false
    const get = vi.spyOn(apiClient, "get").mockImplementation(async (url) => {
      if (url.includes("/produtos/4996")) return concluido ? produtoAtual : produto
      if (url.includes("resultado=erros")) return { count: concluido ? 0 : 1, results: concluido ? [] : [{ ...linha, resultado: "erro", tiny_id: "" }] }
      if (url.includes("resultado=cadastrados")) return { count: concluido ? 1 : 0, results: concluido ? [linha] : [] }
      return { total_cadastrados: concluido ? 1 : 0, total_erros: concluido ? 0 : 1 }
    })
    vi.spyOn(apiClient, "post").mockImplementation(async () => {
      concluido = true
      return fluxo === "atualizar" ? produtoAtual : linha
    })
    const { result, unmount } = renderHook(() => ({
      atualizar: useAtualizarVariacaoTiny(slug),
      retry: useRetentarVariacaoExecucao(slug, "10"),
      produto: useVariacaoInstancia(slug, "4996"),
      resumo: useExecucaoDetalhe(slug, "10"),
      erros: useExecucaoProdutos(slug, "10", { resultado: "erros", page: 1 }),
      cadastrados: useExecucaoProdutos(slug, "10", { resultado: "cadastrados", page: 1 }),
    }), { wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> })
    await waitFor(() => expect(result.current.erros.data?.count).toBe(1))
    await act(async () => { await result.current[fluxo as "atualizar" | "retry"].mutateAsync(4996) })
    await waitFor(() => {
      expect(result.current.erros.data?.count).toBe(0)
      expect(result.current.erros.data?.results).toEqual([])
      expect(result.current.cadastrados.data?.count).toBe(1)
      expect(result.current.resumo.data?.total_erros).toBe(0)
      expect(result.current.resumo.data?.total_cadastrados).toBe(1)
      expect(result.current.produto.data?.tiny_id).toBe("924385783")
    })
    // Uma linha de auditoria NUNCA substitui o objeto VariacaoDetalhe.
    expect(client.getQueryData(chaveProduto)).toEqual(produtoAtual)
    expect(client.getQueryState(chaveOutraExecucao)?.isInvalidated).toBe(true)
    expect(client.getQueryState(chaveOutraInstancia)?.isInvalidated).toBe(false)
    expect(get.mock.calls.filter(([url]) => url.includes("resultado=erros"))).toHaveLength(2)
    unmount()
    client.clear()
  })

  it("erro é propagado sem gravar operação/erro no cache de detalhe", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const chave = ["instancias", "produtos", "detalhe", "loja", "4996"]
    const detalhe = { id: 4996, status: "erro" }
    client.setQueryData(chave, detalhe)
    vi.spyOn(apiClient, "post").mockRejectedValue(new ApiError(409, "conflito XBZ"))
    const { result, unmount } = renderHook(() => useAtualizarVariacaoTiny("loja"), {
      wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    })
    await act(async () => { await expect(result.current.mutateAsync(4996)).rejects.toThrow("conflito XBZ") })
    expect(client.getQueryData(chave)).toEqual(detalhe)
    expect(client.getQueryState(chave)?.isInvalidated).toBe(true)
    unmount()
    client.clear()
  })
})
