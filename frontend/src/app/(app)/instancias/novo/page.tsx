import { Suspense } from "react";
import { WizardInstanciaNova } from "@/components/instancias/wizard/wizard-instancia-nova";

/** Passo 10: assistente de 4 passos (identificação, credenciais, autorização, fornecedores). */
export default function InstanciaNovaPage() {
  return (
    <Suspense>
      <WizardInstanciaNova />
    </Suspense>
  );
}
