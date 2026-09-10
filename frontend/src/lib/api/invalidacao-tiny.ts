import type { QueryClient } from "@tanstack/react-query"

/** Uma variação pode aparecer em várias execuções e páginas filtradas. */
export function invalidarSincronizacaoTiny(client: QueryClient, slug: string, variacaoId?: number) {
  const chaves = [
    ["instancias", "produtos", slug],
    ["instancias", "detalhe", slug],
    ["instancias", "execucoes", slug],
    ["instancias", "execucoes", "detalhe", slug],
    ["instancias", "execucoes", "produtos", slug],
    ["instancias", "execucoes", "produto-logs", slug],
    ["instancias", "produtos", "detalhe", slug, ...(variacaoId ? [String(variacaoId)] : [])],
  ]
  return Promise.all(chaves.map((queryKey) => client.invalidateQueries({ queryKey })))
}
