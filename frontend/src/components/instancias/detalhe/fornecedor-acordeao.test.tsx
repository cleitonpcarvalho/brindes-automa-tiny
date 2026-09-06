import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import * as hooks from "@/lib/api/hooks";
import { FornecedorAcordeao } from "./fornecedor-acordeao";
import type { CadenciaFornecedor, CredencialFornecedorResposta, FornecedorDetalhe, FornecedorEnum } from "@/lib/api/types";

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

interface CasoFornecedor {
  fornecedor: FornecedorEnum;
  campos: { chave: string; rotulo: string; valor: string; sensivel: boolean; obrigatorio: boolean }[];
}

const CASOS: CasoFornecedor[] = [
  {
    fornecedor: "xbz",
    campos: [
      { chave: "cnpj", rotulo: "CNPJ", valor: "11222333000181", sensivel: false, obrigatorio: true },
      { chave: "token", rotulo: "Token", valor: "token-ficticio-de-teste", sensivel: true, obrigatorio: true },
    ],
  },
  {
    fornecedor: "asia",
    campos: [
      { chave: "api_key", rotulo: "API Key", valor: "api-key-ficticia", sensivel: true, obrigatorio: true },
      { chave: "secret_key", rotulo: "Secret Key", valor: "secret-key-ficticia", sensivel: true, obrigatorio: true },
    ],
  },
  {
    fornecedor: "somarcas",
    campos: [
      { chave: "usuario", rotulo: "Usuário", valor: "operador-teste", sensivel: false, obrigatorio: true },
      { chave: "senha", rotulo: "Senha", valor: "senha-ficticia", sensivel: true, obrigatorio: true },
      { chave: "estado", rotulo: "Estado (opcional)", valor: "CE", sensivel: false, obrigatorio: false },
    ],
  },
  {
    fornecedor: "spot",
    campos: [
      { chave: "access_key", rotulo: "Access Key", valor: "access-key-ficticia", sensivel: true, obrigatorio: true },
    ],
  },
];

function renderFornecedor(credencial: CredencialFornecedorResposta) {
  return render(
    <FornecedorAcordeao
      statusDetalhe={fornecedorDetalhe({ fornecedor: credencial.fornecedor })}
      credencial={credencial}
      cadencia={{ ...CADENCIA_XBZ, fornecedor: credencial.fornecedor }}
      slug="loja-x"
      defaultExpanded
    />
  );
}

describe("FornecedorAcordeao", () => {
  it.each(CASOS)("$fornecedor permite configurar campos inicialmente não configurados", ({ fornecedor, campos }) => {
    renderFornecedor({
      fornecedor,
      ativo: false,
      configurado: false,
      campos_mascarados: Object.fromEntries(campos.map((campo) => [campo.chave, null])),
      criado_em: null,
    });

    for (const campo of campos) {
      expect(screen.getByLabelText(campo.rotulo)).toHaveValue("Não configurado");
      expect(screen.getByLabelText(campo.rotulo)).toHaveAttribute("readonly");
    }

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();

    for (const campo of campos) {
      const input = screen.getByLabelText(campo.rotulo);
      expect(input).toHaveValue("");
      expect(input).not.toBeDisabled();
      expect(input).not.toHaveAttribute("readonly");
      expect(input).toHaveAttribute("type", campo.sensivel ? "password" : "text");
      if (campo.obrigatorio) fireEvent.change(input, { target: { value: campo.valor } });
    }

    expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
    const ultimoObrigatorio = campos.filter((campo) => campo.obrigatorio).at(-1)!;
    fireEvent.change(screen.getByLabelText(ultimoObrigatorio.rotulo), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
  });

  it.each(CASOS)("$fornecedor preenche somente públicos e descarta alterações ao cancelar", ({ fornecedor, campos }) => {
    const credencial: CredencialFornecedorResposta = {
      fornecedor,
      ativo: true,
      configurado: true,
      campos_mascarados: Object.fromEntries(campos.map((campo) => [campo.chave, campo.sensivel ? "••••••••123" : campo.valor])),
      criado_em: "2026-01-01T00:00:00Z",
    };
    renderFornecedor(credencial);
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));

    for (const campo of campos) {
      expect(screen.getByLabelText(campo.rotulo)).toHaveValue(campo.sensivel ? "" : campo.valor);
      fireEvent.change(screen.getByLabelText(campo.rotulo), { target: { value: "alteracao-descartada" } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    for (const campo of campos) {
      expect(screen.getByLabelText(campo.rotulo)).toHaveValue(String(credencial.campos_mascarados[campo.chave]));
      expect(screen.getByLabelText(campo.rotulo)).toHaveAttribute("readonly");
    }
    expect(screen.queryByRole("button", { name: "Salvar" })).not.toBeInTheDocument();
    expect(hooks.useAtualizarCredencial).toHaveBeenCalledWith("loja-x", fornecedor);
    const mutacao = vi.mocked(hooks.useAtualizarCredencial).mock.results.at(-1)!.value;
    expect(mutacao.mutateAsync).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    for (const campo of campos) {
      expect(screen.getByLabelText(campo.rotulo)).toHaveValue(campo.sensivel ? "" : campo.valor);
    }
  });

  it("mantém o segundo fornecedor somente leitura enquanto o primeiro é editado", () => {
    renderFornecedor(CREDENCIAL_XBZ);
    renderFornecedor({
      fornecedor: "spot", ativo: true, configurado: true,
      campos_mascarados: { access_key: "••••••••123" }, criado_em: "2026-01-01T00:00:00Z",
    });
    const [xbz, spot] = screen.getAllByRole("article");
    fireEvent.click(within(xbz).getByRole("button", { name: "Editar" }));

    expect(within(xbz).getByLabelText("Token")).not.toHaveAttribute("readonly");
    expect(within(spot).getByLabelText("Access Key")).toHaveAttribute("readonly");
    expect(within(spot).getByRole("button", { name: "Editar" })).toBeInTheDocument();
  });

  it("permite digitar nas credenciais após clicar em Editar", () => {
    render(
      <FornecedorAcordeao
        statusDetalhe={fornecedorDetalhe({})}
        credencial={CREDENCIAL_XBZ}
        cadencia={CADENCIA_XBZ}
        slug="loja-x"
        defaultExpanded
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    const cnpj = screen.getByLabelText("CNPJ");
    const token = screen.getByLabelText("Token");
    fireEvent.change(cnpj, { target: { value: "11222333000181" } });
    fireEvent.change(token, { target: { value: "token-ficticio-de-teste" } });

    expect(cnpj).toHaveValue("11222333000181");
    expect(token).toHaveValue("token-ficticio-de-teste");
    expect(cnpj).not.toHaveAttribute("readonly");
    expect(token).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
  });

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

describe("persistência das credenciais pelo BFF", () => {
  let hooksReais: typeof hooks;
  const clientes: QueryClient[] = [];

  beforeAll(async () => {
    hooksReais = await vi.importActual<typeof hooks>("@/lib/api/hooks");
  });

  beforeEach(() => {
    vi.mocked(hooks.useAtualizarCredencial).mockImplementation(hooksReais.useAtualizarCredencial);
  });

  afterEach(() => {
    clientes.forEach((cliente) => cliente.clear());
    clientes.length = 0;
    vi.unstubAllGlobals();
  });

  const credencialAusente: CredencialFornecedorResposta = {
    fornecedor: "xbz", ativo: false, configurado: false,
    campos_mascarados: { cnpj: null, token: null }, criado_em: null,
  };
  const credencialOutroFornecedor: CredencialFornecedorResposta = {
    fornecedor: "asia", ativo: true, configurado: true,
    campos_mascarados: { api_key: "••••••••111", secret_key: "••••••••222" },
    criado_em: "2026-01-01T00:00:00Z",
  };
  const respostaMascarada: CredencialFornecedorResposta = {
    ...CREDENCIAL_XBZ,
    ativo: false,
    campos_mascarados: { cnpj: "11222333000181", token: "••••••••ste" },
  };

  function CardComConsulta() {
    const consulta = hooksReais.useCredenciais("loja-x");
    return (
      <FornecedorAcordeao
        statusDetalhe={fornecedorDetalhe({ cor: "nao_configurado", credencial_configurada: false, credencial_ativa: false })}
        credencial={consulta.data!.find((credencial) => credencial.fornecedor === "xbz")!}
        cadencia={CADENCIA_XBZ}
        slug="loja-x"
        defaultExpanded
      />
    );
  }

  function prepararEdicao() {
    const cliente = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
    });
    clientes.push(cliente);
    cliente.setQueryData(["instancias", "credenciais", "loja-x"], [credencialAusente, credencialOutroFornecedor]);
    cliente.setQueryData(["instancias", "credenciais", "outra-loja"], [CREDENCIAL_XBZ]);
    cliente.setQueryData(["instancias", "detalhe", "loja-x"], { fornecedores: [fornecedorDetalhe({})] });
    cliente.setQueryData(["instancias", "listagem", {}], { results: [] });
    cliente.setQueryData(["instancias", "cadencias", "loja-x"], [CADENCIA_XBZ]);
    render(<QueryClientProvider client={cliente}><CardComConsulta /></QueryClientProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    fireEvent.change(screen.getByLabelText("CNPJ"), { target: { value: "11222333000181" } });
    fireEvent.change(screen.getByLabelText("Token"), { target: { value: "token-ficticio-de-teste" } });
    return cliente;
  }

  it("envia PUT por instância, preserva ativo e atualiza card/cache com a resposta mascarada antes do refetch", async () => {
    let concluirPut!: (resposta: Response) => void;
    const putPendente = new Promise<Response>((resolve) => { concluirPut = resolve; });
    // Mantém o refetch pendente para comprovar que a resposta do PUT atualiza a tela imediatamente.
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      init?.method === "PUT" ? putPendente : new Promise<Response>(() => {}),
    );
    vi.stubGlobal("fetch", fetchMock);
    const cliente = prepararEdicao();

    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/backend/instancias/loja-x/credenciais/xbz/",
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credenciais: { cnpj: "11222333000181", token: "token-ficticio-de-teste" }, ativo: false }),
      },
    ));
    expect(screen.getByRole("button", { name: "Salvando…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    expect(screen.getByLabelText("Token")).toBeDisabled();
    concluirPut(new Response(JSON.stringify(respostaMascarada), { status: 200 }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Editar" })).toBeInTheDocument());
    expect(screen.getByLabelText("Token")).toHaveValue("••••••••ste");
    expect(screen.getByText("Configurado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sincronizar/ })).toBeDisabled();
    expect(cliente.getQueryData(["instancias", "credenciais", "loja-x"])).toEqual([respostaMascarada, credencialOutroFornecedor]);
    expect(cliente.getQueryData(["instancias", "credenciais", "outra-loja"])).toEqual([CREDENCIAL_XBZ]);
    expect(JSON.stringify(cliente.getQueryCache().getAll().map((consulta) => consulta.state.data))).not.toContain("token-ficticio-de-teste");
    await waitFor(() => expect(JSON.stringify(cliente.getMutationCache().getAll().map((mutacao) => mutacao.state.variables))).not.toContain("token-ficticio-de-teste"));
    for (const chave of ["credenciais", "detalhe", "cadencias"]) {
      expect(cliente.getQueryState(["instancias", chave, "loja-x"])?.isInvalidated).toBe(true);
    }
    expect(cliente.getQueryState(["instancias", "listagem", {}])?.isInvalidated).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(screen.getByLabelText("Token")).toHaveValue("");
    expect(screen.getByLabelText("CNPJ")).toHaveValue("11222333000181");
  });

  it.each([
    { nome: "validação HTTP 400", responder: () => Promise.resolve(new Response(JSON.stringify({ credenciais: ["Campos obrigatórios ausentes: token"] }), { status: 400 })), mensagem: "Confira os campos obrigatórios e informe novamente todos os campos secretos." },
    { nome: "erro HTTP 502", responder: () => Promise.resolve(new Response(JSON.stringify({ detail: "Backend temporariamente indisponível." }), { status: 502 })), mensagem: "Backend temporariamente indisponível." },
    { nome: "falha de rede", responder: () => Promise.reject(new TypeError("Failed to fetch")), mensagem: null },
  ])("mostra $nome e mantém os valores para correção, sem alterar o cache", async ({ responder, mensagem }) => {
    const fetchMock = vi.fn(responder);
    vi.stubGlobal("fetch", fetchMock);
    const cliente = prepararEdicao();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    const alerta = await screen.findByRole("alert");
    if (mensagem) expect(alerta).toHaveTextContent(mensagem);
    else expect(alerta).not.toBeEmptyDOMElement();
    expect(alerta).not.toHaveTextContent("token-ficticio-de-teste");
    expect(screen.getByLabelText("CNPJ")).toHaveValue("11222333000181");
    expect(screen.getByLabelText("Token")).toHaveValue("token-ficticio-de-teste");
    expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
    expect(cliente.getQueryData(["instancias", "credenciais", "loja-x"])).toEqual([credencialAusente, credencialOutroFornecedor]);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    await waitFor(() => expect(JSON.stringify(cliente.getMutationCache().getAll().map((mutacao) => mutacao.state.variables))).not.toContain("token-ficticio-de-teste"));
    expect(screen.getByLabelText("Token")).toHaveValue("Não configurado");
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(screen.getByLabelText("Token")).toHaveValue("");
  });
});
