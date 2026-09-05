"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useLogin } from "@/lib/api/hooks";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    login.mutate(
      { email, password, remember },
      {
        onSuccess: () => {
          const from = searchParams.get("from");
          router.push(from && from.startsWith("/") ? from : "/dashboard");
          router.refresh();
        },
      },
    );
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit} noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="email">E-mail</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor="password">Senha</Label>
          <a
            href="#"
            className="rounded text-caption-label text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            Esqueci minha senha
          </a>
        </div>
        <div className="relative flex items-center">
          <Input
            id="password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="pr-9 font-mono tracking-widest"
          />
          <button
            type="button"
            aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
            onClick={() => setShowPassword((value) => !value)}
            className="absolute right-2.5 flex items-center justify-center rounded text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
      </div>

      <div className="flex items-center pt-0.5">
        <label className="group flex cursor-pointer items-center gap-2 select-none">
          <Checkbox checked={remember} onCheckedChange={(value) => setRemember(value === true)} />
          <span className="text-caption-label text-muted-foreground transition-colors group-hover:text-foreground">
            Manter conectado
          </span>
        </label>
      </div>

      {login.isError && (
        <p role="alert" className="text-caption-label text-error">
          {login.error.message}
        </p>
      )}

      <div className="pt-2">
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? "Entrando…" : "Entrar"}
        </Button>
      </div>
    </form>
  );
}
