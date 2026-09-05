import { Suspense } from "react";
import { RefreshCw } from "lucide-react";
import { LoginForm } from "@/components/auth/login-form";

export default function LoginPage() {
  return (
    <main className="flex h-screen w-full items-center justify-center bg-background p-4">
      <div className="flex w-full max-w-[400px] flex-col items-center">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <RefreshCw size={18} strokeWidth={2.2} />
          </div>
          <h1 className="text-[18px] leading-tight font-semibold tracking-tight text-foreground">Automa Soluct</h1>
          <p className="mt-0.5 text-caption-label text-muted-foreground">Sync ERP</p>
        </div>

        <div className="w-full rounded-xl border border-border bg-card p-6 shadow-xl">
          <div className="mb-5">
            <h2 className="text-title-page-mobile text-foreground">Entrar</h2>
            <p className="mt-1.5 text-caption-label text-muted-foreground">Acesse o painel de sincronização</p>
          </div>

          <Suspense>
            <LoginForm />
          </Suspense>
        </div>

        <div className="mt-6 text-center">
          <p className="text-caption-label tracking-wide text-muted-foreground">
            Acesso restrito · Automa Soluct © {new Date().getFullYear()}
          </p>
        </div>
      </div>
    </main>
  );
}
