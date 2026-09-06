import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { backendUrl, SESSION_COOKIE } from "@/lib/auth/session";

/**
 * Proxy genérico: o navegador nunca fala direto com o Django nem vê o
 * token — ele chama esta rota (mesma origem do Next.js, sem CORS
 * necessário), que injeta o `Authorization: Token <token>` a partir do
 * cookie httpOnly e repassa a chamada de verdade. Isso é o que a tarefa
 * chama de "cliente HTTP que injeta o token": a injeção acontece aqui, no
 * servidor, não no navegador — ver decisão documentada no retorno do passo 7.
 */
async function proxy(request: NextRequest, path: string[]) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;

  const url = new URL(backendUrl(`/${path.join("/")}/`));
  url.search = request.nextUrl.search;

  const headers = new Headers({ "Content-Type": "application/json" });
  if (token) headers.set("Authorization", `Token ${token}`);

  const hasBody = !["GET", "HEAD", "DELETE"].includes(request.method);
  const body = hasBody ? await request.text() : undefined;

  let backendResponse: Response;
  try {
    backendResponse = await fetch(url, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Não foi possível falar com o servidor." }, { status: 502 });
  }

  if (backendResponse.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const responseBody = await backendResponse.text();
  return new NextResponse(responseBody, {
    status: backendResponse.status,
    headers: { "Content-Type": backendResponse.headers.get("Content-Type") ?? "application/json" },
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function PUT(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
