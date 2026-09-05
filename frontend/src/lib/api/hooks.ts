"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type {
  Alerta,
  ExecucaoAtividade,
  Instancia,
  LoginRequest,
  MeResponse,
  PaginatedInstanciaListagem,
  Periodo,
  Resumo,
  StatusInstancia,
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

/** Detalhe de uma instância por slug — usado na tela de detalhe (placeholder no passo 8). */
export function useInstancia(slug: string) {
  return useQuery({
    queryKey: ["instancias", "detalhe", slug],
    queryFn: () => apiClient.get<Instancia>(`/instancias/${slug}`),
    enabled: Boolean(slug),
  });
}
