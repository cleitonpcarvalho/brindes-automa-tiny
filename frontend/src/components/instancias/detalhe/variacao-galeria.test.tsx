import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { VariacaoGaleria } from "./variacao-galeria"

describe("VariacaoGaleria", () => {
  it("mostra o fallback quando não há imagem", () => {
    render(<VariacaoGaleria imagens={[]} alt="Caneca" />)
    expect(screen.getByText("Sem imagem no espelho")).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("mostra só a imagem principal quando há uma única imagem (sem miniaturas)", () => {
    render(<VariacaoGaleria imagens={["https://cdn.exemplo.com/a.jpg"]} alt="Caneca" />)
    const imgs = screen.getAllByRole("img")
    expect(imgs).toHaveLength(1)
    expect(imgs[0]).toHaveAttribute("src", "https://cdn.exemplo.com/a.jpg")
    expect(imgs[0]).toHaveClass("object-contain")
  })

  it("renderiza miniaturas para múltiplas imagens e troca a principal ao clicar", () => {
    render(
      <VariacaoGaleria
        imagens={[
          "https://cdn.exemplo.com/a.jpg",
          "https://cdn.exemplo.com/b.jpg",
          "https://cdn.exemplo.com/c.jpg",
        ]}
        alt="Caneca"
      />,
    )
    const miniaturas = screen.getAllByRole("button", { name: /Ver imagem \d+ de 3/ })
    expect(miniaturas).toHaveLength(3)

    // principal = 1ª imagem, dentro do quadro grande (alt = "Caneca")
    expect(screen.getByAltText("Caneca")).toHaveAttribute("src", "https://cdn.exemplo.com/a.jpg")

    fireEvent.click(miniaturas[2])
    expect(screen.getByAltText("Caneca")).toHaveAttribute("src", "https://cdn.exemplo.com/c.jpg")
  })

  it("cai no fallback quando a imagem principal falha ao carregar", () => {
    render(<VariacaoGaleria imagens={["https://cdn.exemplo.com/quebrada.jpg"]} alt="Caneca" />)
    fireEvent.error(screen.getByAltText("Caneca"))
    expect(screen.getByText("Imagem indisponível")).toBeInTheDocument()
  })
})
