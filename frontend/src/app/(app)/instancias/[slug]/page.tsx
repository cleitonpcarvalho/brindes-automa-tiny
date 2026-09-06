import { Suspense } from "react";
import { use } from "react";
import { InstanciaDetalheView } from "@/components/instancias/detalhe/instancia-detalhe-view";

/** Abas Visão geral, Fornecedores, Produtos e Execuções; Configurações continua placeholder. */
export default function InstanciaDetalhePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);

  return (
    <Suspense>
      <InstanciaDetalheView slug={slug} />
    </Suspense>
  );
}
