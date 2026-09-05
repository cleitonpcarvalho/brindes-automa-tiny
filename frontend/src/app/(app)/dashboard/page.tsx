"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/empty-error-state";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PeriodSelector } from "@/components/dashboard/period-selector";
import { AlertasPanel } from "@/components/dashboard/alertas-panel";
import { AtividadeRecente } from "@/components/dashboard/atividade-recente";
import { InstanciasResumo } from "@/components/dashboard/instancias-resumo";
import { useResumo } from "@/lib/api/hooks";
import { formatarNumero } from "@/lib/format";
import type { Periodo } from "@/lib/api/types";

export default function DashboardPage() {
  const [periodo, setPeriodo] = useState<Periodo>("hoje");
  const { data: resumo, isLoading, isError, refetch } = useResumo(periodo);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-title-page text-foreground">Visão geral</h1>
          <p className="text-body-default text-muted-foreground">
            Monitoramento das sincronizações de catálogo com os ERPs dos clientes
          </p>
        </div>
        <PeriodSelector valor={periodo} onChange={setPeriodo} />
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, indice) => (
            <Skeleton key={indice} className="h-28 rounded-xl" />
          ))}
        </div>
      )}

      {!isLoading && isError && (
        <div className="rounded-xl border border-border bg-card">
          <ErrorState title="Não foi possível carregar o resumo do dashboard." onRetry={() => refetch()} />
        </div>
      )}

      {!isLoading && !isError && resumo && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            titulo="Instâncias ativas"
            valor={`${formatarNumero(resumo.instancias.ativas)}/${formatarNumero(resumo.instancias.total)}`}
            progresso={resumo.instancias.total > 0 ? (resumo.instancias.ativas / resumo.instancias.total) * 100 : 0}
            progressoVariant="primary"
          />
          <MetricCard
            titulo="Produtos sincronizados"
            valor={formatarNumero(resumo.produtos_sincronizados.total)}
            comparacao={`${resumo.produtos_sincronizados.diferenca >= 0 ? "+" : ""}${formatarNumero(
              resumo.produtos_sincronizados.diferenca,
            )} vs período anterior`}
            comparacaoVariant={resumo.produtos_sincronizados.diferenca >= 0 ? "success" : "error"}
          />
          <MetricCard
            titulo="Execuções nas últimas 24h"
            valor={formatarNumero(resumo.execucoes_24h.total)}
            comparacao={`${formatarNumero(resumo.execucoes_24h.sucesso)} com sucesso`}
            comparacaoVariant="success"
            progresso={
              resumo.execucoes_24h.total > 0 ? (resumo.execucoes_24h.sucesso / resumo.execucoes_24h.total) * 100 : 0
            }
            progressoVariant="success"
          />
          <MetricCard
            titulo="Alertas abertos"
            valor={formatarNumero(resumo.alertas.abertos)}
            comparacao={`${formatarNumero(resumo.alertas.requerem_acao)} exigem ação`}
            comparacaoVariant={resumo.alertas.requerem_acao > 0 ? "warning" : "neutral"}
            progresso={resumo.alertas.abertos > 0 ? (resumo.alertas.requerem_acao / resumo.alertas.abertos) * 100 : 0}
            progressoVariant="warning"
          />
        </div>
      )}

      <AlertasPanel />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[60%_40%]">
        <AtividadeRecente />
        <InstanciasResumo />
      </div>
    </div>
  );
}
