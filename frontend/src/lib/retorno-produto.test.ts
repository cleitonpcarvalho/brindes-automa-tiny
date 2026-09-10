import { describe, expect, it } from "vitest"
import { retornoProduto } from "./retorno-produto"

describe("retornoProduto", () => {
  it("preserva a execução, query e fragmento da mesma instância", () => {
    const href = "/instancias/ekk-brindes/execucoes/10?busca=18700-DOU&resultado=erros&page=3#produtos"
    expect(retornoProduto("ekk-brindes", href)).toEqual({ href, rotulo: "Voltar para Execução" })
  })

  it.each([
    undefined, "", "/instancias/ekk-brindes?tab=produtos",
    "https://example.com", "//example.com", "javascript:alert(1)",
    "/instancias/outra/execucoes/10", "/instancias/ekk-brindes/execucoes/10/../../fora",
    "/instancias/ekk-brindes/execucoes/%2e%2e", "/instancias/ekk-brindes/execucoes/10%2f..",
    "/instancias/ekk-brindes/execucoes/10\\example.com",
    "/instancias/ekk-brindes/execucoes/10\n", "/instancias/ekk-brindes/execucoes/10/produtos",
  ])("retorno inválido ou origem produtos (%s) usa fallback seguro", (retorno) => {
    expect(retornoProduto("ekk-brindes", retorno)).toEqual({
      href: "/instancias/ekk-brindes?tab=produtos", rotulo: "Voltar para Produtos",
    })
  })
})
