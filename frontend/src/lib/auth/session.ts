/**
 * A sessão do operador é o token do DRF, guardado num cookie httpOnly —
 * nunca acessível via JavaScript no navegador (mitiga roubo de token por
 * XSS). Só código rodando no servidor Next.js (route handlers, middleware)
 * lê ou grava esse cookie; o navegador só sabe que "tem sessão" pela
 * presença do cookie, nunca pelo valor.
 */

export const SESSION_COOKIE = "session_token";

const UM_DIA_EM_SEGUNDOS = 60 * 60 * 24;

/** "Manter conectado" desmarcado = expira em 1 dia; marcado = 30 dias. */
export function sessionCookieOptions(remember: boolean) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: remember ? UM_DIA_EM_SEGUNDOS * 30 : UM_DIA_EM_SEGUNDOS,
  };
}

export function backendUrl(path: string): string {
  const base = process.env.BACKEND_INTERNAL_URL ?? "http://backend:8000";
  return `${base}/api${path}`;
}
