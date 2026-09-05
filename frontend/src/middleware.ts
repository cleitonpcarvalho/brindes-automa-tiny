import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth/session";

const PUBLIC_PATHS = ["/login"];

function isPublicPath(pathname: string): boolean {
  return (
    PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`)) ||
    pathname.startsWith("/api/auth/")
  );
}

/**
 * Só confere a PRESENÇA do cookie de sessão (rápido, sem chamar o backend a
 * cada navegação). Validade de verdade é responsabilidade do cliente de API
 * no navegador: qualquer chamada que volte 401 derruba a sessão e manda de
 * volta pro login (ver lib/api/client.ts).
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  if (pathname === "/login" && hasSession) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  if (!isPublicPath(pathname) && !hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
