import { Badge } from "@/components/ui/badge"
import { formatarDuracao, formatarNumero, formatarTempoRelativo } from "@/lib/format"
import { ROTULO_FORNECEDOR } from "../cor-fornecedor"
import type { ExecucaoResumida } from "@/lib/api/types"

// `status`/`tipo` vêm como string livre do backend (ExecucaoResumidaSerializer usa
// CharField, não ChoiceField — mesmo padrão de ExecucaoAtividadeSerializer no
// dashboard), por isso os mapas abaixo são indexados por string, com fallback.
const BADGE_POR_STATUS_EXECUCAO: Record<string, { variant: "success" | "error" | "warning" | "neutral"; rotulo: string }> = {
  sucesso: { variant: "success", rotulo: "Sucesso" },
  falha: { variant: "error", rotulo: "Falha" },
  parcial: { variant: "warning", rotulo: "Parcial" },
  rodando: { variant: "neutral", rotulo: "Rodando" },
}

const ROTULO_TIPO: Record<string, string> = {
  carga_inicial: "Carga inicial",
  incremental: "Incremental",
}

function badgeStatus(status: string) {
  return BADGE_POR_STATUS_EXECUCAO[status] ?? { variant: "neutral" as const, rotulo: status };
}

function resultadoTexto(execucao: ExecucaoResumida): string {
  if (execucao.status === "falha") {
    return execucao.mensagem_erro || "Falha sem detalhe registrado";
  }
  return `${formatarNumero(execucao.total_lidos)} lidos · ${formatarNumero(execucao.total_novos)} novos · ${formatarNumero(
    execucao.total_atualizados
  )} atualizados · ${formatarNumero(execucao.total_erros)} erros`;
}

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
                    {formatarTempoRelativo(execucao.iniciada_em)}
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
