import { Suspense } from "react";
import { ExecucoesGlobaisView } from "@/components/global/execucoes-globais-view";

export default function SincronizacoesPage() {
  return (
    <Suspense>
      <ExecucoesGlobaisView variante="sincronizacoes" />
    </Suspense>
  );
}
