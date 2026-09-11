import { Badge } from "@/components/ui/badge"
import { formatarDataHora, formatarDuracao, formatarTempoRelativo } from "@/lib/format"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import { ROTULO_TIPO, badgeStatus, resultadoTexto } from "./execucao-formato"
import type { ExecucaoResumida } from "@/lib/api/types"

export function ExecucoesTabela({ execucoes }: { execucoes: ExecucaoResumida[] }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl bg-card p-4">
      <div>
        <h2 className="text-header-section text-foreground">Últimas execuções</h2>
        <p className="text-caption-label text-muted-foreground">Histórico recente de sincronização desta conta</p>
      </div>

      {execucoes.length === 0 ? (
        <p className="py-6 text-center text-caption-label text-muted-foreground">Nenhuma execução ainda.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="h-8 bg-secondary text-caption-medium text-muted-foreground">
                <th className="px-3 font-medium">Iniciada em</th>
                <th className="px-3 font-medium">Fornecedor</th>
                <th className="px-3 font-medium">Tipo</th>
                <th className="px-3 font-medium">Resultado</th>
                <th className="px-3 text-right font-medium">Duração</th>
                <th className="px-3 text-center font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {execucoes.map((execucao) => (
                <tr
                  key={execucao.id}
                  className={`h-10 text-body-default ${execucao.status === "falha" ? "bg-error-subtle/40" : ""}`}
                >
                  <td className="px-3 font-mono text-[13px] text-foreground">
                    <span title={formatarDataHora(execucao.iniciada_em, true)}>
                      {formatarDataHora(execucao.iniciada_em)}
                      <span className="ml-1 text-muted-foreground">({formatarTempoRelativo(execucao.iniciada_em)})</span>
                    </span>
                  </td>
                  <td className="px-3">
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-code-inline text-foreground">
                      {ROTULO_FORNECEDOR[execucao.fornecedor]}
                    </span>
                  </td>
                  <td className="px-3 text-caption-label text-muted-foreground">
                    {ROTULO_TIPO[execucao.tipo] ?? execucao.tipo}
                  </td>
                  <td
                    className={`max-w-[340px] truncate px-3 font-mono text-[13px] ${execucao.status === "falha" ? "text-error" : "text-foreground"}`}
                  >
                    {resultadoTexto(execucao)}
                  </td>
                  <td className="px-3 text-right font-mono text-[13px] text-muted-foreground">
                    {formatarDuracao(execucao.duracao_segundos)}
                  </td>
                  <td className="px-3 text-center">
                    <Badge variant={badgeStatus(execucao.status).variant}>{badgeStatus(execucao.status).rotulo}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
