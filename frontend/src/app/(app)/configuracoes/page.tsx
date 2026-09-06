import { Suspense } from "react";
import { ConfiguracoesGlobaisView } from "@/components/global/configuracoes-globais-view";

export default function ConfiguracoesPage() {
  return (
    <Suspense>
      <ConfiguracoesGlobaisView />
    </Suspense>
  );
}
