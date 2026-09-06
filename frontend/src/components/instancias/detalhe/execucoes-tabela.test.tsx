import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExecucoesTabela } from "./execucoes-tabela";
import type { ExecucaoResumida } from "@/lib/api/types";

function execucao(overrides: Partial<ExecucaoResumida>): ExecucaoResumida {
  return {
    id: 1,
    fornecedor: "xbz",
    tipo: "incremental",
    status: "sucesso",
    iniciada_em: new Date(Date.now() - 40 * 60_000).toISOString(),
    finalizada_em: new Date().toISOString(),
    duracao_segundos: 48,
    total_lidos: 1156,
    total_novos: 4,
    total_atualizados: 12,
    total_erros: 0,
    mensagem_erro: "",
    ...overrides,
  };
}

describe("ExecucoesTabela", () => {
  it("mostra o estado vazio quando não há execuções", () => {
    render(<ExecucoesTabela execucoes={[]} />);
    expect(screen.getByText("Nenhuma execução ainda.")).toBeInTheDocument();
  });

  it("renderiza o badge Sucesso e a contagem de resultado", () => {
    render(<ExecucoesTabela execucoes={[execucao({ status: "sucesso" })]} />);
    expect(screen.getByText("Sucesso")).toBeInTheDocument();
    expect(screen.getByText("1.156 lidos · 4 novos · 12 atualizados · 0 erros")).toBeInTheDocument();
  });

  it("renderiza o badge Falha e a mensagem de erro em vez das contagens", () => {
    render(
      <ExecucoesTabela
        execucoes={[execucao({ status: "falha", mensagem_erro: "HTTP 401 Unauthorized", total_lidos: 0 })]}
      />
    );
    expect(screen.getByText("Falha")).toBeInTheDocument();
    expect(screen.getByText("HTTP 401 Unauthorized")).toBeInTheDocument();
  });

  it("renderiza o badge Parcial", () => {
    render(<ExecucoesTabela execucoes={[execucao({ status: "parcial", total_erros: 3 })]} />);
    expect(screen.getByText("Parcial")).toBeInTheDocument();
  });

  it("renderiza o badge Rodando", () => {
    render(<ExecucoesTabela execucoes={[execucao({ status: "rodando", finalizada_em: null, duracao_segundos: null })]} />);
    expect(screen.getByText("Rodando")).toBeInTheDocument();
  });
});
