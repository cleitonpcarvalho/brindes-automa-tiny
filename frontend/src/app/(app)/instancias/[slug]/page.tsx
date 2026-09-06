import { Suspense } from "react";
import { use } from "react";
import { InstanciaDetalheView } from "@/components/instancias/detalhe/instancia-detalhe-view";

/** Passo 10: abas Visão geral e Fornecedores; Produtos/Execuções/Configurações continuam placeholder. */
export default function InstanciaDetalhePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);

  return (
    <Suspense>
      <InstanciaDetalheView slug={slug} />
    </Suspense>
  );
}
