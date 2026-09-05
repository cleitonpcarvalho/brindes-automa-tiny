import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { backendUrl, sessionCookieOptions, SESSION_COOKIE } from "@/lib/auth/session";
import type { components } from "@/lib/api/schema";

type LoginRequest = components["schemas"]["LoginRequest"] & { remember?: boolean };
type LoginResponse = components["schemas"]["LoginResponse"];
type ErrorResponse = components["schemas"]["ErrorResponse"];

export async function POST(request: Request) {
  const { remember, ...credentials } = (await request.json()) as LoginRequest;

  let backendResponse: Response;
  try {
    backendResponse = await fetch(backendUrl("/auth/login/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json<ErrorResponse>(
      { detail: "Não foi possível falar com o servidor. Tente novamente." },
      { status: 502 },
    );
  }

  if (!backendResponse.ok) {
    const error = (await backendResponse.json().catch(() => ({ detail: "Falha ao entrar." }))) as ErrorResponse;
    return NextResponse.json(error, { status: backendResponse.status });
  }

  const data = (await backendResponse.json()) as LoginResponse;

  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, data.token, sessionCookieOptions(remember ?? false));

  return NextResponse.json({ email: data.email, nome: data.nome });
}
