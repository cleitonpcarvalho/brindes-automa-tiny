/** Aceita exclusivamente a execução numérica da mesma instância. */
export function retornoProduto(slug: string, retorno?: string) {
  const fallback = { href: `/instancias/${slug}?tab=produtos`, rotulo: "Voltar para Produtos" }
  const prefixo = `/instancias/${slug}/execucoes/`
  if (!retorno?.startsWith(prefixo) || retorno.includes("\\") ||
      [...retorno].some((char) => char.charCodeAt(0) < 32)) return fallback
  const [caminho] = retorno.split(/[?#]/)
  if (!/^\d+$/.test(caminho.slice(prefixo.length))) return fallback
  return { href: retorno, rotulo: "Voltar para Execução" }
}
