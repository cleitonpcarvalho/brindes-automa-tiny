"use client";

/**
 * Cliente HTTP tipado usado pelos hooks do TanStack Query. Fala sempre com
 * `/api/backend/*` (mesma origem do Next.js — ver app/api/backend/[...path]),
 * nunca direto com o Django: o token vive num cookie httpOnly que só o
 * servidor Next.js lê, então o navegador não tem como injetá-lo sozinho.
 *
 * 401/403 aqui sempre significam "a sessão não serve mais" (token ausente,
 * expirado ou revogado) — derruba a sessão e manda pro login, de qualquer
 * tela em que isso aconteça.
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let sessionExpiredHandlerRunning = false;

async function handleSessionExpired() {
  if (sessionExpiredHandlerRunning) return;
  sessionExpiredHandlerRunning = true;
  await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
  window.location.href = "/login";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (response.status === 401 || response.status === 403) {
    void handleSessionExpired();
    throw new ApiError(response.status, "Sessão expirada. Faça login novamente.");
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(response.status, body.detail ?? "Ocorreu um erro inesperado.");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
