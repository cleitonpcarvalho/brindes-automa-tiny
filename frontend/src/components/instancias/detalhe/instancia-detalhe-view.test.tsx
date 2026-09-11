import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as hooks from "@/lib/api/hooks";
import { InstanciaDetalheView } from "./instancia-detalhe-view";
import type { InstanciaDetalhe } from "@/lib/api/types";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(mockSearchParams),
}));

let mockSearchParams = "";

vi.mock("@/lib/api/hooks", () => ({
  useInstancia: vi.fn(),
  useCredenciais: vi.fn(),
  useCadencias: vi.fn(),
  useSincronizarFornecedor: vi.fn(),
  useAutorizar: vi.fn(),
  useDesconectar: vi.fn(),
  useAtualizarCredencial: vi.fn(),
  useAtualizarTinyFornecedorId: vi.fn(),
  useAtualizarCadencia: vi.fn(),
  useCadastroTinyPreview: vi.fn(),
  useCadastrarProdutosTiny: vi.fn(),
  usePausarCadastroTiny: vi.fn(),
  useRetomarCadastroTiny: vi.fn(),
}));

function mutacaoParada() {
  return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, error: null, reset: vi.fn() } as never;
}

function instanciaDetalhe(): InstanciaDetalhe {
  return {
    id: 1,
    nome: "Loja X",
    cnpj: "11.222.333/0001-44",
    slug: "loja-x",
    client_id: "cid",
    status: "conectado",
    tentativas_falha: 0,
    ultimo_erro: "",
    access_token_preenchido: "true",
    refresh_token_preenchido: "true",
    token_emitido_em: null,
    token_expira_em: null,
    refresh_expira_em: null,
    rate_limit_por_minuto: null,
    tiny_origem_padrao: null,
    tiny_unidade_medida_padrao: "",
    url_callback: "https://sync-api.automasoluct.com.br/api/tiny/oauth/callback/loja-x",
    criado_em: "2026-01-01T00:00:00Z",
    atualizado_em: "2026-01-01T00:00:00Z",
    produtos: { total: 0, cadastrados: 0, aguardando: 0, com_erro: 0 },
    fornecedores: (["xbz", "asia", "somarcas", "spot"] as const).map((fornecedor) => ({
      fornecedor,
      cor: "nao_configurado" as const,
      ultima_execucao_em: null,
      ultima_execucao_status: null,
      ultima_execucao: null,
      produtos_total: 0,
      produtos_aguardando: 0,
      produtos_descontinuados: 0,
      credencial_configurada: false,
      credencial_ativa: false,
      cadastro_tiny: {
        execucao_id: null,
        estado: "pronto" as const,
        total_lidos: 0,
        total_cadastrados: 0,
        total_erros: 0,
        total_ignorados: 0,
        progresso: 0,
        atualizada_em: null,
        mensagem_erro: "",
        motivo_status: "",
        bloqueados: 0,
        falhas_secundarias: 0,
        pode_iniciar: true,
        pode_pausar: false,
        pode_retomar: false,
      },
    })),
    cadencias: [
      { fornecedor: "xbz", intervalo_minutos: 60, ativo: false, propagar_tiny: false, proxima_execucao_em: null },
      { fornecedor: "asia", intervalo_minutos: 60, ativo: false, propagar_tiny: false, proxima_execucao_em: null },
      { fornecedor: "somarcas", intervalo_minutos: 60, ativo: false, propagar_tiny: false, proxima_execucao_em: null },
      { fornecedor: "spot", intervalo_minutos: 60, ativo: false, propagar_tiny: false, proxima_execucao_em: null },
    ],
    ultimas_execucoes: [],
  };
}

describe("InstanciaDetalheView", () => {
  beforeEach(() => {
    mockSearchParams = "";
    replace.mockClear();
    vi.mocked(hooks.useInstancia).mockReturnValue({
      data: instanciaDetalhe(),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never);
    vi.mocked(hooks.useCredenciais).mockReturnValue({
      data: instanciaDetalhe().fornecedores.map((f) => ({
        fornecedor: f.fornecedor,
        ativo: false,
        configurado: false,
        campos_mascarados: {},
        tiny_fornecedor_id: null,
        criado_em: null,
      })),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never);
    vi.mocked(hooks.useCadencias).mockReturnValue({
      data: instanciaDetalhe().cadencias,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never);
    vi.mocked(hooks.useSincronizarFornecedor).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.useAutorizar).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.useDesconectar).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.useAtualizarCredencial).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.useAtualizarTinyFornecedorId).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.useAtualizarCadencia).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.useCadastrarProdutosTiny).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.usePausarCadastroTiny).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.useRetomarCadastroTiny).mockReturnValue(mutacaoParada());
    vi.mocked(hooks.useCadastroTinyPreview).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as never);
  });

  it("sem ?autorizado=1 abre na aba Visão geral e não mostra o banner de sucesso", () => {
    render(<InstanciaDetalheView slug="loja-x" />);
    expect(screen.queryByText(/autorizada com sucesso/)).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Visão geral" })).toHaveAttribute("data-state", "active");
  });

  it("com ?autorizado=1 mostra o banner de sucesso e abre direto na aba Fornecedores", () => {
    mockSearchParams = "autorizado=1";
    render(<InstanciaDetalheView slug="loja-x" />);

    expect(screen.getByText(/autorizada com sucesso/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Fornecedores" })).toHaveAttribute("data-state", "active");
  });
});
