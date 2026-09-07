import { formatarNumero } from "@/lib/format"

/**
 * Formatação compartilhada de execuções — usada tanto pela tabela "Últimas
 * execuções" da Visão geral quanto pelo histórico completo da aba Execuções.
 *
 * `status`/`tipo` chegam como enum do backend, mas os mapas são indexados por
 * string com fallback (mesmo padrão de ExecucaoAtividade no dashboard).
 */

export const BADGE_POR_STATUS_EXECUCAO: Record<
  string,
  { variant: "success" | "error" | "warning" | "neutral"; rotulo: string }
> = {
  sucesso: { variant: "success", rotulo: "Sucesso" },
  falha: { variant: "error", rotulo: "Falha" },
  parcial: { variant: "warning", rotulo: "Parcial" },
  rodando: { variant: "neutral", rotulo: "Rodando" },
}

export const ROTULO_TIPO: Record<string, string> = {
  carga_inicial: "Carga inicial",
  incremental: "Incremental",
  cadastro_tiny: "Cadastro no Tiny",
}

export function badgeStatus(status: string) {
  return BADGE_POR_STATUS_EXECUCAO[status] ?? { variant: "neutral" as const, rotulo: status }
}

/** Campos mínimos que `resultadoTexto` lê — satisfeito por ExecucaoResumida e Execucao. */
interface ExecucaoResultado {
  status?: string
  mensagem_erro?: string
  total_lidos?: number
  total_novos?: number
  total_atualizados?: number
  total_erros?: number
}

export function resultadoTexto(execucao: ExecucaoResultado): string {
  if (execucao.status === "falha") {
    return execucao.mensagem_erro || "Falha sem detalhe registrado"
  }
  return `${formatarNumero(execucao.total_lidos ?? 0)} lidos · ${formatarNumero(
    execucao.total_novos ?? 0,
  )} novos · ${formatarNumero(execucao.total_atualizados ?? 0)} atualizados · ${formatarNumero(
    execucao.total_erros ?? 0,
  )} erros`
}
