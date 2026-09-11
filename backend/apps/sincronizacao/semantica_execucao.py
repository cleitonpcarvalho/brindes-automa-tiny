from .models import StatusExecucao, TipoExecucao


def _motivo_status(execucao, *, auditoria_resumo=None):
    if execucao.mensagem_erro:
        return execucao.mensagem_erro
    if execucao.status == StatusExecucao.INTERROMPIDO:
        return "Execução interrompida; o motivo detalhado não foi registrado."
    if execucao.status == StatusExecucao.PAUSADO:
        return "Execução pausada e disponível para retomada."
    if execucao.status == StatusExecucao.PAUSANDO:
        return "Execução em processo de pausa."
    if execucao.status == StatusExecucao.PARCIAL:
        if execucao.tipo == TipoExecucao.CADASTRO_TINY:
            falhas_secundarias = (auditoria_resumo or {}).get("falhas_secundarias", 0)
            detalhe_secundario = (
                f" e {falhas_secundarias} falha(s) secundária(s) (imagem/anexo)"
                if falhas_secundarias else ""
            )
            return (
                f"Execução parcial: {execucao.total_erros or 0} erro(s) e "
                f"{execucao.total_ignorados or 0} item(ns) ignorado(s) ou pendente(s)"
                f"{detalhe_secundario}."
            )
        return f"Importação parcial: {execucao.total_erros or 0} erro(s) registrado(s)."
    if execucao.status == StatusExecucao.FALHA:
        return "Execução encerrada com falha, sem detalhe adicional registrado."
    if execucao.status == StatusExecucao.SUCESSO:
        return "Execução concluída com sucesso."
    return ""


def _auditoria_cadastro(execucao):
    from . import auditoria

    return auditoria.resumo_auditoria(execucao)


def montar_semantica_execucao(execucao, *, auditoria_resumo=None):
    """Métricas e progresso coerentes com o tipo, somente para leitura da UI."""
    logs_individuais = getattr(execucao, "logs_individuais_total", None)
    if logs_individuais is None:
        logs_individuais = execucao.logs.filter(variacao__isnull=False).count()

    resumo_para_motivo = auditoria_resumo
    if execucao.tipo == TipoExecucao.CADASTRO_TINY:
        resumo = auditoria_resumo or _auditoria_cadastro(execucao)
        resumo_para_motivo = resumo
        metricas = [
            {"chave": "total_fila", "rotulo": "Total da fila", "valor": resumo["total"]},
            {
                "chave": "cadastrados",
                "rotulo": "Cadastrados",
                "valor": resumo["cadastrados_e_vinculados"],
            },
            {"chave": "erros", "rotulo": "Erros", "valor": resumo["erros"]},
            {
                "chave": "ignorados",
                "rotulo": "Ignorados / bloqueados",
                "valor": resumo["bloqueados"],
            },
        ]
        if resumo.get("falhas_secundarias", 0):
            metricas.append({
                "chave": "falhas_secundarias",
                "rotulo": "Falhas secundárias (imagem/anexo)",
                "valor": resumo["falhas_secundarias"],
            })
        total = resumo["total"]
        concluido = resumo["cadastrados_e_vinculados"] + resumo["erros"] + resumo["bloqueados"]
        progresso = round(min(concluido / total, 1.0), 4) if total else None
    else:
        metricas = [
            {"chave": "lidos", "rotulo": "Itens lidos", "valor": execucao.total_lidos or 0},
            {"chave": "novos", "rotulo": "Novos", "valor": execucao.total_novos or 0},
            {
                "chave": "atualizados",
                "rotulo": "Atualizados",
                "valor": execucao.total_atualizados or 0,
            },
            {
                "chave": "ignorados",
                "rotulo": "Ignorados / sem alteração",
                "valor": execucao.total_ignorados or 0,
            },
            {"chave": "erros", "rotulo": "Erros", "valor": execucao.total_erros or 0},
        ]
        # Uma importação não possui denominador incremental confiável enquanto
        # está rodando. Encerrada, ela é uma operação concluída, não um cadastro
        # Tiny parcialmente processado.
        progresso = 1.0 if execucao.finalizada_em and execucao.total_lidos else None

    if progresso is not None:
        progresso_rotulo = f"{round(progresso * 100)}%"
    elif execucao.finalizada_em:
        progresso_rotulo = "Concluída"
    else:
        progresso_rotulo = "Sem percentual disponível"

    return {
        "metricas": metricas,
        "progresso": progresso,
        "progresso_rotulo": progresso_rotulo,
        "motivo_status": _motivo_status(execucao, auditoria_resumo=resumo_para_motivo),
        "logs_individuais_total": logs_individuais,
        "mensagem_logs": (
            "Logs individuais por SKU disponíveis."
            if logs_individuais
            else "Esta execução não possui processamento individual por SKU."
        ),
    }
