import { describe, expect, it } from "vitest"
import { apresentarAtributo, humanizarChave } from "./atributo-formato"

describe("apresentarAtributo", () => {
  it("string simples → o próprio texto (trim)", () => {
    expect(apresentarAtributo("porcelana")).toBe("porcelana")
    expect(apresentarAtributo("  9608.10.00  ")).toBe("9608.10.00")
  })

  it("número → texto do número", () => {
    expect(apresentarAtributo(15)).toBe("15")
    expect(apresentarAtributo(6.5)).toBe("6.5")
    expect(apresentarAtributo(0)).toBe("0")
  })

  it("boolean → Sim / Não", () => {
    expect(apresentarAtributo(true)).toBe("Sim")
    expect(apresentarAtributo(false)).toBe("Não")
  })

  it("objeto com value → o value (caso Asia Import)", () => {
    expect(
      apresentarAtributo({ name: "Branco", value: "Branco", hexadecimal: "#fff" }),
    ).toBe("Branco")
    expect(apresentarAtributo({ name: "15l", value: "15L" })).toBe("15L")
    expect(
      apresentarAtributo({ name: "cinza", value: "Cinza", hexadecimal: "#7f7f7f" }),
    ).toBe("Cinza")
  })

  it("objeto só com name (sem value) → o name", () => {
    expect(apresentarAtributo({ name: "Azul", hexadecimal: "#00f" })).toBe("Azul")
  })

  it("objeto sem value/name mas com label/descrição → o rótulo", () => {
    expect(apresentarAtributo({ label: "Grande" })).toBe("Grande")
    expect(apresentarAtributo({ descricao: "Contra defeitos" })).toBe("Contra defeitos")
  })

  it("array → itens apresentados e unidos por vírgula", () => {
    expect(apresentarAtributo(["EN71", "Ftalatos"])).toBe("EN71, Ftalatos")
    expect(
      apresentarAtributo([{ value: "Azul" }, { name: "Vermelho" }, "Verde"]),
    ).toBe("Azul, Vermelho, Verde")
    expect(apresentarAtributo(["ok", "", null, "  "])).toBe("ok")
  })

  it("null / undefined / vazio → travessão", () => {
    expect(apresentarAtributo(null)).toBe("—")
    expect(apresentarAtributo(undefined)).toBe("—")
    expect(apresentarAtributo("")).toBe("—")
    expect(apresentarAtributo("   ")).toBe("—")
    expect(apresentarAtributo([])).toBe("—")
    expect(apresentarAtributo({})).toBe("—")
  })

  it("objeto desconhecido → 'chave: valor' legível, nunca JSON cru nem [object Object]", () => {
    const saida = apresentarAtributo({ largura_cm: 30, material: "algodão", reciclado: true })
    expect(saida).not.toContain("[object Object]")
    expect(saida).not.toContain("{")
    expect(saida).not.toContain('"')
    expect(saida).toContain("largura cm: 30")
    expect(saida).toContain("material: algodão")
    expect(saida).toContain("reciclado: Sim")
  })

  it("objeto aninhado desconhecido → não despeja JSON e não trava", () => {
    const saida = apresentarAtributo({ dados: { a: { b: 1 } }, nota: "x" })
    expect(saida).not.toContain("[object Object]")
    expect(saida).not.toContain("{")
    expect(saida).toContain("nota: x")
  })

  it("NaN / Infinity não viram texto quebrado", () => {
    expect(apresentarAtributo(Number.NaN)).toBe("—")
    expect(apresentarAtributo(Number.POSITIVE_INFINITY)).toBe("—")
  })
})

describe("humanizarChave", () => {
  it("troca separadores por espaço e quebra camelCase", () => {
    expect(humanizarChave("volume-litros")).toBe("volume litros")
    expect(humanizarChave("codigo_composto")).toBe("codigo composto")
    expect(humanizarChave("quantidade_minima_sugerida")).toBe("quantidade minima sugerida")
    expect(humanizarChave("garantiaDoProduto")).toBe("garantia Do Produto")
  })
})
