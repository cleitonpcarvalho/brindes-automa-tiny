"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type {
  Alerta,
  AutorizarResposta,
  CadenciaFornecedor,
  ConfiguracoesInstancia,
  CredencialFornecedorResposta,
  ExecucaoAtividade,
  FornecedorEnum,
  Instancia,
  InstanciaDetalhe,
  LoginRequest,
  MeResponse,
  ExecucaoDetalhe,
  PaginatedExecucaoList,
  PaginatedExecucaoProdutoList,
  PaginatedInstanciaListagem,
  PaginatedLogItemList,
  PaginatedVariacaoEspelhoList,
  PatchedConfiguracoesInstancia,
  Periodo,
  Resumo,
  CadastroTinyPreview,
  SincronizarResposta,
  StatusExecucao,
  StatusInstancia,
  StatusVariacao,
  VariacaoDetalhe,
} from "./types";

/** Sessão do operador — também serve para confirmar que o token ainda é válido. */
export function useMe() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiClient.get<MeResponse>("/auth/me"),
    retry: false,
  });
}

/**
 * Login não passa pelo apiClient: ele não injeta token (ainda não existe
 * um) e a resposta precisa ser tratada pela rota de login do Next.js, que
 * grava o cookie httpOnly — por isso chama /api/auth/login diretamente.
 */
export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: LoginRequest & { remember?: boolean }) => {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string } & Partial<MeResponse>;
      if (!response.ok) {
        throw new Error(data.detail ?? "Não foi possível entrar.");
      }
      return data as MeResponse;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["auth", "me"], data);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await fetch("/api/auth/logout", { method: "POST" });
    },
    onSuccess: () => {
      queryClient.clear();
      window.location.href = "/login";
    },
  });
}

/** Resumo do dashboard — os quatro números do topo (passo 8). */
export function useResumo(periodo: Periodo = "hoje") {
  return useQuery({
    queryKey: ["dashboard", "resumo", periodo],
    queryFn: () => apiClient.get<Resumo>(`/dashboard/resumo?periodo=${periodo}`),
  });
}

/** O que precisa de atenção agora — derivado do estado atual (passo 8). */
export function useAlertas() {
  return useQuery({
    queryKey: ["dashboard", "alertas"],
    queryFn: () => apiClient.get<Alerta[]>("/dashboard/alertas"),
  });
}

/** As últimas execuções de todas as instâncias (passo 8). */
export function useAtividade(limit = 10) {
  return useQuery({
    queryKey: ["dashboard", "atividade", limit],
    queryFn: () => apiClient.get<ExecucaoAtividade[]>(`/dashboard/atividade?limit=${limit}`),
  });
}

export interface FiltrosInstancias {
  busca?: string;
  status?: StatusInstancia | "";
  page?: number;
  pageSize?: number;
}

/** Listagem paginada de instâncias, com busca/status/ordenação (passo 8). */
export function useInstanciasListagem(filtros: FiltrosInstancias = {}) {
  const params = new URLSearchParams();
  if (filtros.busca) params.set("busca", filtros.busca);
  if (filtros.status) params.set("status", filtros.status);
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.pageSize) params.set("page_size", String(filtros.pageSize));
  const query = params.toString();

  return useQuery({
    queryKey: ["instancias", "listagem", filtros],
    queryFn: () =>
      apiClient.get<PaginatedInstanciaListagem>(`/instancias${query ? `?${query}` : ""}`),
    placeholderData: (dadosAnteriores) => dadosAnteriores,
  });
}

/**
 * Detalhe de uma instância por slug — traz os agregados da tela de detalhe
 * (passo 10). Enquanto houver alguma sincronização "rodando" (ex.: a carga
 * inicial de um fornecedor), refaz a consulta a cada 4s para a tela mostrar
 * o andamento/resultado sem depender de refresh manual — não é uma barra de
 * progresso, é o estado real vindo da Execucao.
 */
/**
 * Há alguma sincronização em curso (importação de espelho `rodando`, ou
 * cadastro Tiny `sincronizando`/`pausando`) em algum fornecedor da
 * instância? Enquanto sim, o detalhe faz polling — é assim que o progresso
 * incremental da sincronização Tiny chega à tela (o backend persiste os
 * contadores a cada ~5s; a UI busca a cada 4s).
 */
export function instanciaTemSincronizacaoAtiva(instancia: InstanciaDetalhe | undefined): boolean {
  return (instancia?.fornecedores ?? []).some(
    (f) =>
      f.ultima_execucao_status === "rodando" ||
      f.cadastro_tiny.estado === "sincronizando" ||
      f.cadastro_tiny.estado === "pausando",
  );
}

export function useInstancia(slug: string) {
  return useQuery({
    queryKey: ["instancias", "detalhe", slug],
    queryFn: () => apiClient.get<InstanciaDetalhe>(`/instancias/${slug}`),
    enabled: Boolean(slug),
    refetchInterval: (query) =>
      instanciaTemSincronizacaoAtiva(query.state.data) ? 4000 : false,
  });
}

export interface FiltrosProdutos {
  busca?: string;
  fornecedor?: FornecedorEnum | "";
  status?: StatusVariacao | "";
  page?: number;
  pageSize?: number;
}

/**
 * Aba Produtos do detalhe — variações (SKUs) do espelho local desta
 * instância, paginadas no servidor. Só consulta; nenhuma sincronização.
 */
export function useProdutosInstancia(slug: string, filtros: FiltrosProdutos = {}) {
  const params = new URLSearchParams();
  if (filtros.busca) params.set("busca", filtros.busca);
  if (filtros.fornecedor) params.set("fornecedor", filtros.fornecedor);
  if (filtros.status) params.set("status", filtros.status);
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.pageSize) params.set("page_size", String(filtros.pageSize));
  const query = params.toString();

  return useQuery({
    queryKey: ["instancias", "produtos", slug, filtros],
    queryFn: () =>
      apiClient.get<PaginatedVariacaoEspelhoList>(
        `/instancias/${slug}/produtos${query ? `?${query}` : ""}`,
      ),
    enabled: Boolean(slug),
    placeholderData: (dadosAnteriores) => dadosAnteriores,
  });
}

/**
 * Detalhe de UMA variação (SKU) do espelho local desta instância — a tela
 * /instancias/<slug>/produtos/<id>. Só consulta; nenhuma sincronização,
 * nada é escrito no Tiny. 404 (variação inexistente ou de outra instância)
 * chega como ApiError e a tela mostra o estado "não encontrada".
 */
export function useVariacaoInstancia(slug: string, variacaoId: string | number) {
  return useQuery({
    queryKey: ["instancias", "produtos", "detalhe", slug, String(variacaoId)],
    queryFn: () =>
      apiClient.get<VariacaoDetalhe>(`/instancias/${slug}/produtos/${variacaoId}`),
    enabled: Boolean(slug && variacaoId),
    retry: false,
  });
}

export interface FiltrosExecucoes {
  fornecedor?: FornecedorEnum | "";
  status?: StatusExecucao | "";
  page?: number;
  pageSize?: number;
}

/**
 * Aba Execuções do detalhe — histórico paginado (server-side) das rodadas de
 * sincronização desta instância. Só observabilidade; nenhuma ação.
 */
export function useExecucoesInstancia(slug: string, filtros: FiltrosExecucoes = {}) {
  const params = new URLSearchParams();
  if (filtros.fornecedor) params.set("fornecedor", filtros.fornecedor);
  if (filtros.status) params.set("status", filtros.status);
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.pageSize) params.set("page_size", String(filtros.pageSize));
  const query = params.toString();

  return useQuery({
    queryKey: ["instancias", "execucoes", slug, filtros],
    queryFn: () =>
      apiClient.get<PaginatedExecucaoList>(
        `/instancias/${slug}/execucoes${query ? `?${query}` : ""}`,
      ),
    enabled: Boolean(slug),
    placeholderData: (dadosAnteriores) => dadosAnteriores,
  });
}

/**
 * Logs de UMA execução, para o modal de detalhes. Busca uma página grande de
 * uma vez (a UI não pagina os logs) e só dispara quando há execução selecionada.
 */
export function useExecucaoLogs(slug: string, execucaoId: number | null) {
  return useQuery({
    queryKey: ["instancias", "execucoes", "logs", slug, execucaoId],
    queryFn: () =>
      apiClient.get<PaginatedLogItemList>(
        `/instancias/${slug}/execucoes/${execucaoId}/logs?page_size=200`,
      ),
    enabled: Boolean(slug && execucaoId),
  });
}

/**
 * Resumo da execução para o topo da tela de auditoria. Enquanto estiver
 * rodando/pausando, faz polling de 4s — o MESMO mecanismo do detalhe da
 * instância, sem nada novo.
 */
export function useExecucaoDetalhe(slug: string, execucaoId: string | number) {
  return useQuery({
    queryKey: ["instancias", "execucoes", "detalhe", slug, String(execucaoId)],
    queryFn: () =>
      apiClient.get<ExecucaoDetalhe>(`/instancias/${slug}/execucoes/${execucaoId}`),
    enabled: Boolean(slug && execucaoId),
    retry: false,
    refetchInterval: (query) => {
      const estado = query.state.data?.estado;
      return estado === "sincronizando" || estado === "pausando" || estado === "rodando"
        ? 4000
        : false;
    },
  });
}

export interface FiltrosExecucaoProdutos {
  busca?: string;
  resultado?: "cadastrados" | "erros" | "bloqueados" | "";
  page?: number;
  pageSize?: number;
}

/** Tabela de auditoria por SKU de uma execução — paginada no servidor. */
export function useExecucaoProdutos(
  slug: string,
  execucaoId: string | number,
  filtros: FiltrosExecucaoProdutos = {},
) {
  const params = new URLSearchParams();
  if (filtros.busca) params.set("busca", filtros.busca);
  if (filtros.resultado) params.set("resultado", filtros.resultado);
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.pageSize) params.set("page_size", String(filtros.pageSize));
  const query = params.toString();

  return useQuery({
    queryKey: ["instancias", "execucoes", "produtos", slug, String(execucaoId), filtros],
    queryFn: () =>
      apiClient.get<PaginatedExecucaoProdutoList>(
        `/instancias/${slug}/execucoes/${execucaoId}/produtos${query ? `?${query}` : ""}`,
      ),
    enabled: Boolean(slug && execucaoId),
    placeholderData: (anterior) => anterior,
  });
}

/** Logs técnicos (com detalhe/JSON) de UM SKU nesta execução — para o expand da linha. */
export function useExecucaoProdutoLogs(
  slug: string,
  execucaoId: string | number,
  variacaoId: number | null,
) {
  return useQuery({
    queryKey: ["instancias", "execucoes", "produto-logs", slug, String(execucaoId), variacaoId],
    queryFn: () =>
      apiClient.get<PaginatedLogItemList>(
        `/instancias/${slug}/execucoes/${execucaoId}/produtos/${variacaoId}`,
      ),
    enabled: Boolean(slug && execucaoId && variacaoId),
  });
}

/** Logs técnicos gerais (início/pausa/conclusão) — a seção secundária da tela. */
export function useExecucaoLogsGerais(slug: string, execucaoId: string | number, { enabled = true } = {}) {
  return useQuery({
    queryKey: ["instancias", "execucoes", "logs-gerais", slug, String(execucaoId)],
    queryFn: () =>
      apiClient.get<PaginatedLogItemList>(
        `/instancias/${slug}/execucoes/${execucaoId}/logs?escopo=gerais&page_size=200`,
      ),
    enabled: Boolean(slug && execucaoId) && enabled,
  });
}

/** Aba Configurações — só os campos operacionais do Tiny editáveis (origem, unidade). */
export function useConfiguracoesInstancia(slug: string) {
  return useQuery({
    queryKey: ["instancias", "configuracoes", slug],
    queryFn: () =>
      apiClient.get<ConfiguracoesInstancia>(`/instancias/${slug}/configuracoes/`),
    enabled: Boolean(slug),
  });
}

/** Salva (PATCH) as configurações do Tiny — endpoint estreito, não toca campos sensíveis. */
export function useAtualizarConfiguracoes(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dados: PatchedConfiguracoesInstancia) =>
      apiClient.patch<ConfiguracoesInstancia>(`/instancias/${slug}/configuracoes/`, dados),
    onSuccess: (dados) => {
      queryClient.setQueryData(["instancias", "configuracoes", slug], dados);
      queryClient.invalidateQueries({ queryKey: ["instancias", "configuracoes", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "listagem"] });
    },
  });
}

interface DadosInstancia {
  nome: string;
  cnpj?: string;
  client_id: string;
  client_secret: string;
}

/** Passo 1/2 do wizard: cria a instância — é aqui que o slug nasce (passo 10). */
export function useCriarInstancia() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dados: DadosInstancia) => apiClient.post<Instancia>("/instancias/", dados),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instancias", "listagem"] });
    },
  });
}

/** Editar identificação/credenciais de uma instância já criada (link "Editar" do wizard). */
export function useAtualizarInstancia(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dados: Partial<DadosInstancia>) => apiClient.patch<Instancia>(`/instancias/${slug}/`, dados),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "listagem"] });
    },
  });
}

/** Passo 3 do wizard: gera a URL de autorização do Tiny (state novo a cada chamada). */
export function useAutorizar(slug: string) {
  return useMutation({
    mutationFn: () => apiClient.get<AutorizarResposta>(`/instancias/${slug}/autorizar/`),
  });
}

/** Botão "Desconectar" do detalhe — limpa os tokens, mantém a instância. */
export function useDesconectar(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<Instancia>(`/instancias/${slug}/desconectar/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "listagem"] });
    },
  });
}

/** Aba Fornecedores — credenciais mascaradas dos 4 fornecedores (nunca em texto pleno se sensíveis). */
export function useCredenciais(slug: string) {
  return useQuery({
    queryKey: ["instancias", "credenciais", slug],
    queryFn: () => apiClient.get<CredencialFornecedorResposta[]>(`/instancias/${slug}/credenciais/`),
    enabled: Boolean(slug),
  });
}

interface DadosCredencial {
  credenciais: Record<string, string>;
  ativo?: boolean;
}

/** Salva (upsert) a credencial de um fornecedor — nunca ecoa o valor enviado de volta. */
export function useAtualizarCredencial(slug: string, fornecedor: FornecedorEnum) {
  const queryClient = useQueryClient();
  return useMutation({
    // Não retém as credenciais enviadas depois de resetar/desmontar o formulário.
    gcTime: 0,
    mutationFn: (dados: DadosCredencial) =>
      apiClient.put<CredencialFornecedorResposta>(`/instancias/${slug}/credenciais/${fornecedor}/`, dados),
    onSuccess: async (credencialSalva) => {
      // Descarta leituras em voo antes de aplicar a resposta mascarada do PUT.
      await queryClient.cancelQueries({ queryKey: ["instancias", "credenciais", slug], exact: true });
      queryClient.setQueryData<CredencialFornecedorResposta[]>(
        ["instancias", "credenciais", slug],
        (credenciais) => credenciais?.map((credencial) =>
          credencial.fornecedor === fornecedor ? credencialSalva : credencial),
      );
      queryClient.invalidateQueries({ queryKey: ["instancias", "credenciais", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "listagem"] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "cadencias", slug] });
    },
  });
}

/** Aba Fornecedores — cadência (intervalo/ativo) dos 4 fornecedores, com defaults quando ainda não configurada. */
export function useCadencias(slug: string) {
  return useQuery({
    queryKey: ["instancias", "cadencias", slug],
    queryFn: () => apiClient.get<CadenciaFornecedor[]>(`/instancias/${slug}/cadencias/`),
    enabled: Boolean(slug),
  });
}

interface DadosCadencia {
  intervalo_minutos?: number;
  ativo?: boolean;
}

export function useAtualizarCadencia(slug: string, fornecedor: FornecedorEnum) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dados: DadosCadencia) =>
      apiClient.patch<CadenciaFornecedor>(`/instancias/${slug}/cadencias/${fornecedor}/`, dados),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instancias", "cadencias", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] });
    },
  });
}

/**
 * Estimativa (sem tocar no Tiny) para a tela de confirmação do "Sincronizar
 * com Tiny": quantos produtos elegíveis, se a instância está pronta, se já
 * há uma sincronização rodando. Só busca quando habilitado (o dialog abriu).
 */
export function useCadastroTinyPreview(
  slug: string,
  fornecedor: FornecedorEnum,
  { enabled = true }: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: ["instancias", "cadastro-tiny", "preview", slug, fornecedor],
    queryFn: () =>
      apiClient.get<CadastroTinyPreview>(
        `/instancias/${slug}/fornecedores/${fornecedor}/cadastro-tiny/preview`,
      ),
    enabled: Boolean(slug && fornecedor) && enabled,
  });
}

/**
 * Agenda a sincronização em massa de produtos deste fornecedor com o Tiny.
 * O backend cria a Execucao e enfileira a task; a request devolve o id na
 * hora e o processamento (que cria produtos no Tiny) roda em background.
 */
export function useCadastrarProdutosTiny(slug: string, fornecedor: FornecedorEnum) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<SincronizarResposta>(
        `/instancias/${slug}/fornecedores/${fornecedor}/cadastro-tiny/`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "execucoes", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "cadastro-tiny", "preview", slug] });
    },
  });
}

function useAcaoCadastroTiny(slug: string, fornecedor: FornecedorEnum, acao: "pausar" | "retomar") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<SincronizarResposta>(
        `/instancias/${slug}/fornecedores/${fornecedor}/cadastro-tiny/${acao}/`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "execucoes", slug] });
    },
  });
}

/** Pausa cooperativa da sincronização em andamento (não mata a task). */
export function usePausarCadastroTiny(slug: string, fornecedor: FornecedorEnum) {
  return useAcaoCadastroTiny(slug, fornecedor, "pausar");
}

/** Retoma a MESMA execução pausada/interrompida — continua o trabalho pendente. */
export function useRetomarCadastroTiny(slug: string, fornecedor: FornecedorEnum) {
  return useAcaoCadastroTiny(slug, fornecedor, "retomar");
}

/** Dispara a sincronização manual de um fornecedor — devolve o id da execução na hora. */
export function useSincronizarFornecedor(slug: string, fornecedor: FornecedorEnum) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<SincronizarResposta>(`/instancias/${slug}/fornecedores/${fornecedor}/sincronizar/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instancias", "detalhe", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "execucoes", slug] });
      queryClient.invalidateQueries({ queryKey: ["instancias", "listagem"] });
    },
  });
}
