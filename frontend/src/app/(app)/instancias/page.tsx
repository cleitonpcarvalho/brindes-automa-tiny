"use client";

import { useEffect, useState } from "react";
import { InstanciasToolbar } from "@/components/instancias/instancias-toolbar";
import { StatusStrip } from "@/components/instancias/status-strip";
import { InstanciasTable } from "@/components/instancias/instancias-table";
import { PaginationFooter } from "@/components/instancias/pagination-footer";
import { useInstanciasListagem } from "@/lib/api/hooks";
import type { StatusInstancia } from "@/lib/api/types";

const TAMANHO_PAGINA = 10;

export default function InstanciasPage() {
  const [buscaInput, setBuscaInput] = useState("");
  const [busca, setBusca] = useState("");
  const [status, setStatus] = useState<StatusInstancia | "">("");
  const [pagina, setPagina] = useState(1);

  // Debounce simples: evita disparar uma busca a cada tecla digitada.
  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaInput), 300);
    return () => clearTimeout(temporizador);
  }, [buscaInput]);

  useEffect(() => {
    setPagina(1);
  }, [busca, status]);

  const { data, isLoading, isError, refetch } = useInstanciasListagem({
    busca,
    status,
    page: pagina,
    pageSize: TAMANHO_PAGINA,
  });

  const totalPaginas = data ? Math.max(1, Math.ceil(data.count / TAMANHO_PAGINA)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1 border-b border-border pb-6">
        <h1 className="text-title-page text-foreground">Instâncias</h1>
        <p className="text-body-default text-muted-foreground">
          Todas as contas do Tiny sincronizadas com os fornecedores
        </p>
      </div>

      <InstanciasToolbar busca={buscaInput} onBuscaChange={setBuscaInput} status={status} onStatusChange={setStatus} />

      <StatusStrip total={data?.count ?? 0} />

      <InstanciasTable
        itens={data?.results ?? []}
        isLoading={isLoading}
        isError={isError}
        onRetry={() => refetch()}
      />

      {!isLoading && !isError && data && (
        <PaginationFooter
          pagina={pagina}
          totalPaginas={totalPaginas}
          totalItens={data.count}
          itensNaPagina={data.results.length}
          onPageChange={setPagina}
        />
      )}
    </div>
  );
}
