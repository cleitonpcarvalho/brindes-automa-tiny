import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AlertasPanel } from "./alertas-panel";
import * as hooks from "@/lib/api/hooks";

vi.mock("@/lib/api/hooks", () => ({
  useAlertas: vi.fn(),
}));

describe("AlertasPanel", () => {
  it("mostra estado vazio quando a lista de alertas está vazia", () => {
    vi.mocked(hooks.useAlertas).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never);

    render(<AlertasPanel />);

    expect(screen.getByText("Nenhum alerta aberto")).toBeInTheDocument();
    expect(screen.getByText("Tudo sincronizando normalmente.")).toBeInTheDocument();
    expect(screen.getByText("Precisam da sua atenção")).toBeInTheDocument();
    // sem contador quando a lista está vazia
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("mostra estado de carregamento com skeletons", () => {
    vi.mocked(hooks.useAlertas).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    } as never);

    const { container } = render(<AlertasPanel />);
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it("mostra estado de erro com botão de tentar de novo", () => {
    vi.mocked(hooks.useAlertas).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    } as never);

    render(<AlertasPanel />);
    expect(screen.getByText("Não foi possível carregar os alertas.")).toBeInTheDocument();
  });

  it("renderiza um alerta com a ação sugerida", () => {
    vi.mocked(hooks.useAlertas).mockReturnValue({
      data: [
        {
          id: "a1",
          severidade: "critica",
          tipo: "token_expirado",
          instancia: { slug: "loja-x", nome: "Loja X" },
          fornecedor: null,
          mensagem: "Token expirou",
          momento: new Date().toISOString(),
          acao_sugerida: { tipo: "reautorizar", rotulo: "Reautorizar" },
        },
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never);

    render(<AlertasPanel />);
    expect(screen.getByText("Loja X")).toBeInTheDocument();
    expect(screen.getByText("Token expirou")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reautorizar" })).toBeInTheDocument();
  });
});
