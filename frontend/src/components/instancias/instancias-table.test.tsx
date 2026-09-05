import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InstanciasTable } from "./instancias-table";
import type { InstanciaListagem } from "@/lib/api/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function criarInstancia(overrides: Partial<InstanciaListagem>): InstanciaListagem {
  return {
    id: 1,
    nome: "Loja",
    cnpj: "11.222.333/0001-44",
    slug: "loja",
    client_id: "",
    status: "conectado",
    tentativas_falha: 0,
    ultimo_erro: "",
    access_token_preenchido: "",
    refresh_token_preenchido: "",
    token_expira_em: null,
    refresh_expira_em: null,
    rate_limit_por_minuto: null,
    tiny_origem_padrao: null,
    tiny_unidade_medida_padrao: "",
    url_callback: "",
    criado_em: "2026-01-01T00:00:00Z",
    atualizado_em: "2026-01-01T00:00:00Z",
    fornecedores: { xbz: "nao_configurado", asia: "nao_configurado", somarcas: "nao_configurado", spot: "nao_configurado" },
    produtos: { total: 0, cadastrados: 0 },
    ultima_sincronizacao: { em: null, fornecedor: null },
    ...overrides,
  };
}

describe("InstanciasTable", () => {
  it("renderiza cada status de instância com o rótulo correto", () => {
    const itens = [
      criarInstancia({ slug: "conectada", nome: "Loja Conectada", status: "conectado" }),
      criarInstancia({ slug: "com-erro", nome: "Loja com Erro", status: "erro" }),
      criarInstancia({ slug: "sem-conexao", nome: "Loja Sem Conexão", status: "nao_conectado" }),
    ];

    render(<InstanciasTable itens={itens} isLoading={false} isError={false} onRetry={() => {}} />);

    expect(screen.getByText("Loja Conectada")).toBeInTheDocument();
    expect(screen.getByText("Conectada")).toBeInTheDocument();

    expect(screen.getByText("Loja com Erro")).toBeInTheDocument();
    expect(screen.getByText("Erro")).toBeInTheDocument();

    expect(screen.getByText("Loja Sem Conexão")).toBeInTheDocument();
    expect(screen.getByText("Não conectada")).toBeInTheDocument();
  });

  it("mostra estado de carregamento com skeletons", () => {
    const { container } = render(<InstanciasTable itens={[]} isLoading={true} isError={false} onRetry={() => {}} />);
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it("mostra estado de erro com botão de tentar de novo", () => {
    render(<InstanciasTable itens={[]} isLoading={false} isError={true} onRetry={() => {}} />);
    expect(screen.getByText("Não foi possível carregar as instâncias.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
  });

  it("mostra estado vazio quando não há instâncias", () => {
    render(<InstanciasTable itens={[]} isLoading={false} isError={false} onRetry={() => {}} />);
    expect(screen.getByText("Nenhuma instância encontrada")).toBeInTheDocument();
  });

  it("mostra a cor de cada fornecedor e os contadores de produtos", () => {
    const itens = [
      criarInstancia({
        slug: "completa",
        nome: "Loja Completa",
        fornecedores: { xbz: "ok", asia: "atencao", somarcas: "erro", spot: "nao_configurado" },
        produtos: { total: 42, cadastrados: 30 },
        ultima_sincronizacao: { em: new Date().toISOString(), fornecedor: "xbz" },
      }),
    ];

    render(<InstanciasTable itens={itens} isLoading={false} isError={false} onRetry={() => {}} />);

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("30 cadastrados")).toBeInTheDocument();
    expect(screen.getAllByText("XBZ").length).toBeGreaterThan(0);
  });
});
