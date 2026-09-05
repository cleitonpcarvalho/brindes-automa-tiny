import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { backendUrl, SESSION_COOKIE } from "@/lib/auth/session";

export async function POST() {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;

  if (token) {
    // Apaga o token no Django também — não só esquece o cookie local, mas
    // invalida a sessão de verdade (qualquer outro lugar usando o mesmo
    // token para de funcionar). Falha aqui não impede o logout local.
    await fetch(backendUrl("/auth/logout/"), {
      method: "POST",
      headers: { Authorization: `Token ${token}` },
      cache: "no-store",
    }).catch(() => {});
  }

  cookieStore.delete(SESSION_COOKIE);
  return NextResponse.json({ ok: true });
}
