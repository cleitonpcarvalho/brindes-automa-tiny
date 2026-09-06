import { Clock, Info } from "lucide-react"
import { formatarIntervalo, formatarTempoAte } from "@/lib/format"
import { DOT_POR_COR, ROTULO_FORNECEDOR } from "../cor-fornecedor"
import type { CadenciaFornecedor, FornecedorDetalhe } from "@/lib/api/types"

interface Props {
  cadencias: CadenciaFornecedor[]
  fornecedores: FornecedorDetalhe[]
}

export function CadenciaCard({ cadencias, fornecedores }: Props) {
  const corPorFornecedor = Object.fromEntries(fornecedores.map((f) => [f.fornecedor, f.cor]))

  return (
    <div className="flex flex-col justify-between gap-3 rounded-xl bg-card p-4 lg:col-span-5">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between pb-1">
          <div>
            <h2 className="text-header-section text-foreground">Cadência configurada</h2>
            <p className="text-caption-label text-muted-foreground">Agendamento de leitura</p>
          </div>
          <Clock size={18} className="text-muted-foreground" />
        </div>

        <div className="flex flex-col gap-1">
          {cadencias.map((cadencia) => {
            const cor = corPorFornecedor[cadencia.fornecedor] ?? "nao_configurado"
            const texto = !cadencia.ativo
              ? "inativa"
              : cor === "erro"
                ? "em pausa (erro)"
                : formatarTempoAte(cadencia.proxima_execucao_em)

            return (
              <div key={cadencia.fornecedor} className="flex items-center justify-between rounded bg-secondary p-2">
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-code-inline font-medium text-foreground">
                  {ROTULO_FORNECEDOR[cadencia.fornecedor]}
                </span>
                <span className="text-body-default text-foreground">{formatarIntervalo(cadencia.intervalo_minutos)}</span>
                <span className={`flex items-center gap-1 text-caption-label ${cor === "erro" ? "text-error" : "text-muted-foreground"}`}>
                  <span className={`size-1.5 rounded-full ${DOT_POR_COR[cor]}`} />
                  {texto}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      <div className="flex items-center gap-2 rounded bg-secondary p-2 text-caption-label text-muted-foreground">
        <Info size={16} className="text-warning" />
        <span>A XBZ permite no máximo 24 consultas por dia.</span>
      </div>
    </div>
  )
}
