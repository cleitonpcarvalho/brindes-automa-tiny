import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as hooks from "@/lib/api/hooks";
import { FornecedorAcordeao } from "./fornecedor-acordeao";
import type { CadenciaFornecedor, CredencialFornecedorResposta, FornecedorDetalhe } from "@/lib/api/types";

vi.mock("@/lib/api/hooks", () => ({
  useSincronizarFornecedor: vi.fn(),
  useAtualizarCredencial: vi.fn(),
  useAtualizarCadencia: vi.fn(),
}));

function mutacaoParada() {
  return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, error: null, reset: vi.fn() } as never;
}

beforeEach(() => {
  vi.mocked(hooks.useSincronizarFornecedor).mockReturnValue(mutacaoParada());
  vi.mocked(hooks.useAtualizarCredencial).mockReturnValue(mutacaoParada());
  vi.mocked(hooks.useAtualizarCadencia).mockReturnValue(mutacaoParada());
});

const CADENCIA_XBZ: CadenciaFornecedor = { fornecedor: "xbz", intervalo_minutos: 60, ativo: true, proxima_execucao_em: null };

const CREDENCIAL_XBZ: CredencialFornecedorResposta = {
  fornecedor: "xbz",
  ativo: true,
  configurado: true,
  campos_mascarados: { cnpj: "23948964000161", token: "••••••••BF9" },
  criado_em: "2026-01-01T00:00:00Z",
};

function fornecedorDetalhe(overrides: Partial<FornecedorDetalhe>): FornecedorDetalhe {
  return {
    fornecedor: "xbz",
    cor: "ok",
    ultima_execucao_em: "2026-01-01T00:00:00Z",
    ultima_execucao_status: "sucesso",
    produtos_total: 1156,
    credencial_configurada: true,
    credencial_ativa: true,
    ...overrides,
  };
}

describe("FornecedorAcordeao", () => {
  it("mostra o campo não sensível (cnpj) em texto pleno e o sensível (token) mascarado, quando expandido", () => {
    render(
      <FornecedorAcordeao
        statusDetalhe={fornecedorDetalhe({})}
        credencial={CREDENCIAL_XBZ}
        cadencia={CADENCIA_XBZ}
        slug="loja-x"
        defaultExpanded
      />
    );

    expect(screen.getByDisplayValue("23948964000161")).toBeInTheDocument();
    expect(screen.getByDisplayValue("••••••••BF9")).toBeInTheDocument();
  });

  it("mostra a tarja de erro quando o fornecedor está com falha e recolhido", () => {
    render(
      <FornecedorAcordeao
        statusDetalhe={fornecedorDetalhe({ cor: "erro", ultima_execucao_status: "falha" })}
        credencial={CREDENCIAL_XBZ}
        cadencia={CADENCIA_XBZ}
        mensagemErroUltimaExecucao="HTTP 401 Unauthorized"
        slug="loja-x"
        defaultExpanded={false}
      />
    );

    expect(screen.getByText(/Falha na última execução/)).toBeInTheDocument();
    expect(screen.getByText(/HTTP 401 Unauthorized/)).toBeInTheDocument();
  });

  it("não mostra tarja quando o fornecedor está saudável", () => {
    render(
      <FornecedorAcordeao
        statusDetalhe={fornecedorDetalhe({})}
        credencial={CREDENCIAL_XBZ}
        cadencia={CADENCIA_XBZ}
        slug="loja-x"
        defaultExpanded={false}
      />
    );

    expect(screen.queryByText(/Falha na última execução/)).not.toBeInTheDocument();
  });

  it("desabilita o botão Sincronizar quando não há credencial ativa", () => {
    render(
      <FornecedorAcordeao
        statusDetalhe={fornecedorDetalhe({ cor: "nao_configurado", credencial_ativa: false, ultima_execucao_em: null, ultima_execucao_status: null })}
        credencial={{ ...CREDENCIAL_XBZ, ativo: false, configurado: false, campos_mascarados: { cnpj: null, token: null } }}
        cadencia={CADENCIA_XBZ}
        slug="loja-x"
      />
    );

    expect(screen.getByRole("button", { name: /Sincronizar/ })).toBeDisabled();
  });
});
