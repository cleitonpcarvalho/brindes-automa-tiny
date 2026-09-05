"use client";

import Link from "next/link";
import { use } from "react";
import { ArrowLeft } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useInstancia } from "@/lib/api/hooks";

/**
 * Placeholder (passo 8): a rota existe e resolve a instância pelo slug,
 * mas o conteúdo real (produtos, execuções, credenciais por fornecedor)
 * chega no passo 9.
 */
export default function InstanciaDetalhePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const { data: instancia, isLoading } = useInstancia(slug);

  return (
    <div className="flex flex-col gap-4">
      <Link
        href="/instancias"
        className="flex w-fit items-center gap-1.5 text-caption-label text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Voltar para instâncias
      </Link>

      <div className="flex flex-col gap-1 border-b border-border pb-6">
        {isLoading ? (
          <Skeleton className="h-8 w-64" />
        ) : (
          <h1 className="text-title-page text-foreground">{instancia?.nome ?? slug}</h1>
        )}
        <p className="text-body-default text-muted-foreground">Detalhe da instância</p>
      </div>

      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-border bg-card py-16 text-center">
        <p className="text-body-medium text-foreground">Tela em construção</p>
        <p className="max-w-md text-caption-label text-muted-foreground">
          O detalhe completo desta instância (produtos, execuções e credenciais por fornecedor) chega no próximo
          passo.
        </p>
      </div>
    </div>
  );
}
