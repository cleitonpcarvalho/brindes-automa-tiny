from .models import StatusExecucao, TipoExecucao


def _motivo_status(execucao, *, auditoria_resumo=None, tentativa_resumo=None):
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
            fonte = tentativa_resumo or auditoria_resumo or {}
            falhas_secundarias = fonte.get("falhas_secundarias", 0)
            detalhe_secundario = (
                f" e {falhas_secundarias} falha(s) secundária(s) (imagem/anexo)"
                if falhas_secundarias else ""
            )
            return (
                f"Execução parcial: {fonte.get('erros', 0)} erro(s) e "
                f"{fonte.get('bloqueados', 0)} item(ns) ignorado(s) ou pendente(s)"
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
    tentativa_resumo = None
    if execucao.tipo == TipoExecucao.CADASTRO_TINY:
        from . import auditoria

        resumo = auditoria_resumo or _auditoria_cadastro(execucao)
        tentativa_resumo = auditoria.resumo_tentativa_cadastro(execucao)
        if tentativa_resumo and not tentativa_resumo["retomada"]:
            tentativa_resumo = None
        resumo_para_motivo = resumo
        fonte = tentativa_resumo or {
            "total_fila": resumo["total"],
            "processados": resumo["total"],
            "cadastrados": resumo["cadastrados_e_vinculados"],
            "vinculados": 0,
            "bloqueados": resumo["bloqueados"],
            "erros": resumo["erros"],
            "falhas_secundarias": resumo.get("falhas_secundarias", 0),
        }
        metricas = [
            {"chave": "total_fila", "rotulo": "Total da fila desta tentativa", "valor": fonte["total_fila"]},
            {"chave": "processados", "rotulo": "Itens processados nesta tentativa", "valor": fonte["processados"]},
            {
                "chave": "cadastrados",
                "rotulo": "Novos/vinculados nesta tentativa",
                "valor": fonte["cadastrados"] + fonte.get("vinculados", 0),
            },
            {"chave": "erros", "rotulo": "Erros", "valor": fonte["erros"]},
            {
                "chave": "ignorados",
                "rotulo": "Ignorados / bloqueados",
                "valor": fonte["bloqueados"],
            },
        ]
        if fonte.get("falhas_secundarias", 0):
            metricas.append({
                "chave": "falhas_secundarias",
                "rotulo": "Falhas secundárias (imagem/anexo)",
                "valor": fonte["falhas_secundarias"],
            })
        total = fonte["total_fila"]
        progresso = round(min(fonte["processados"] / total, 1.0), 4) if total else None
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
        "motivo_status": _motivo_status(
            execucao,
            auditoria_resumo=resumo_para_motivo,
            tentativa_resumo=tentativa_resumo,
        ),
        "logs_individuais_total": logs_individuais,
        "mensagem_logs": (
            (
                f"{tentativa_resumo['processados']} SKU(s) processado(s) nesta tentativa; "
                "a fila retomada continha operações de imagem."
                if tentativa_resumo and tentativa_resumo["operacoes_imagem"]
                else "Logs individuais por SKU disponíveis."
                if logs_individuais
                else "Esta execução não possui processamento individual por SKU."
            )
        ),
    }
