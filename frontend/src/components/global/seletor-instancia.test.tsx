import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { SeletorInstancia } from "./seletor-instancia"
import type { InstanciaListagem } from "@/lib/api/types"

function inst(slug: string, nome: string): InstanciaListagem {
  return { slug, nome } as unknown as InstanciaListagem
}

describe("SeletorInstancia", () => {
  it("uma instância: mostra o nome como rótulo estático (sem combobox)", () => {
    render(<SeletorInstancia instancias={[inst("ekk", "EKK Brindes")]} slug="ekk" onChange={vi.fn()} />)
    expect(screen.getByText("EKK Brindes")).toBeInTheDocument()
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument()
  })

  it("nenhuma instância: mostra travessão", () => {
    render(<SeletorInstancia instancias={[]} slug="" onChange={vi.fn()} />)
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("várias instâncias: mostra um combobox com as opções", () => {
    render(
      <SeletorInstancia
        instancias={[inst("a", "Loja A"), inst("b", "Loja B")]}
        slug="a"
        onChange={vi.fn()}
      />,
    )
    const combobox = screen.getByRole("combobox")
    expect(combobox).toBeInTheDocument()
    expect(combobox).toHaveTextContent("Loja A")
  })
})
