/**
 * Apresentação segura de um valor de atributo de fornecedor.
 *
 * Os normalizadores guardam em `Variacao.atributos` / `Produto.atributos` o
 * que cada fornecedor manda — e nem sempre é texto plano. A Asia Import, por
 * exemplo, guarda objetos: `{"name":"Branco","value":"Branco","hexadecimal":"#fff"}`
 * ou `{"name":"15l","value":"15L"}`. Isso NÃO pode chegar cru na tela.
 *
 * Esta função é SÓ transformação de exibição — não altera nada armazenado,
 * nenhum payload. Regras:
 *   - string / número / boolean  → o próprio valor (boolean vira "Sim"/"Não");
 *   - objeto com `value` não vazio → esse `value`;
 *   - senão objeto com `name` não vazio → esse `name`;
 *   - senão objeto com `label`/`titulo`/`descricao` → esse rótulo;
 *   - array → itens apresentados (recursivo), sem os vazios, unidos por ", ";
 *   - outro objeto → pares "chave: valor" legíveis (raso), nunca JSON cru
 *     nem "[object Object]";
 *   - null / undefined / vazio / objeto sem nada aproveitável → "—".
 */

const TRACO = "—"

export function apresentarAtributo(valor: unknown): string {
  const texto = formatar(valor, 0)
  return texto === "" ? TRACO : texto
}

function formatar(valor: unknown, profundidade: number): string {
  const simples = primitivo(valor)
  if (simples !== null) return simples

  if (Array.isArray(valor)) {
    return valor
      .map((item) => formatar(item, profundidade + 1))
      .filter((item) => item !== "")
      .join(", ")
  }

  if (valor !== null && typeof valor === "object") {
    const objeto = valor as Record<string, unknown>

    for (const chave of ["value", "name", "label", "titulo", "descricao", "description"]) {
      const candidato = primitivo(objeto[chave])
      if (candidato) return candidato
    }

    // Objeto arbitrário: só descemos um nível para não virar dump recursivo.
    if (profundidade >= 1) return ""

    return Object.entries(objeto)
      .map(([chave, item]) => {
        const apresentado = formatar(item, profundidade + 1)
        return apresentado === "" ? "" : `${humanizarChave(chave)}: ${apresentado}`
      })
      .filter((parte) => parte !== "")
      .join(" · ")
  }

  return ""
}

/** Texto de um valor primitivo, ou `null` se não for primitivo aproveitável. */
function primitivo(valor: unknown): string | null {
  if (typeof valor === "string") return valor.trim()
  if (typeof valor === "number") return Number.isFinite(valor) ? String(valor) : ""
  if (typeof valor === "boolean") return valor ? "Sim" : "Não"
  return null
}

/**
 * Rótulo legível para a CHAVE de um atributo ("volume-litros" -> "volume
 * litros", "codigo_composto" -> "codigo composto"). Só apresentação — a
 * chave real no dado não muda.
 */
export function humanizarChave(chave: string): string {
  return chave
    .replace(/[_-]+/g, " ")
    .replace(/([a-z\d])([A-Z])/g, "$1 $2")
    .trim()
}
