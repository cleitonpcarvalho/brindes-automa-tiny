import { Suspense } from "react";
import { ExecucoesGlobaisView } from "@/components/global/execucoes-globais-view";

export default function LogsPage() {
  return (
    <Suspense>
      <ExecucoesGlobaisView variante="logs" />
    </Suspense>
  );
}
