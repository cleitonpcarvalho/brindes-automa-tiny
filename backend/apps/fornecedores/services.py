"""
Regras compartilhadas entre o comando `importar_fornecedor` (CLI) e a API de
sincronização manual (passo 10) — extraídas do comando para que os dois
caminhos apliquem exatamente a mesma checagem, sem duplicar a lógica nem a
mensagem de erro.
"""

from django.utils import timezone

from apps.instancias.constants import Fornecedor
from apps.instancias.models import CredencialFornecedor
from apps.sincronizacao.models import Execucao, StatusExecucao

from .models import CadenciaFornecedor, ConfiguracaoFornecedor


def checar_limite_diario_xbz(instancia, fornecedor, force=False):
    """
    Regra do cliente: xbz tem limite de 24 chamadas/dia, compartilhado com o
    cliente final — nunca repetir sem querer no mesmo dia. Levanta ValueError
    (não CommandError: esta função também é chamada pela API, que não tem
    esse conceito) — cada chamador traduz para o que fizer sentido.
    """
    if fornecedor != Fornecedor.XBZ or force:
        return
    ja_rodou_hoje = Execucao.objects.filter(
        instancia=instancia,
        fornecedor=fornecedor,
        status__in=[StatusExecucao.SUCESSO, StatusExecucao.PARCIAL],
        iniciada_em__date=timezone.localdate(),
    ).exists()
    if ja_rodou_hoje:
        raise ValueError(
            "xbz já foi importado hoje para esta instância. Use --force para repetir "
            "(lembre-se do limite de 24 chamadas/dia, compartilhado com o cliente final)."
        )


def obter_credencial_ativa(instancia, fornecedor):
    try:
        return CredencialFornecedor.objects.get(instancia=instancia, fornecedor=fornecedor, ativo=True)
    except CredencialFornecedor.DoesNotExist:
        raise ValueError(
            f"Não há credencial ativa de '{fornecedor}' para a instância '{instancia}'."
        ) from None


def obter_configuracao(fornecedor):
    config = ConfiguracaoFornecedor.objects.filter(fornecedor=fornecedor).first()
    return {"url_base_imagens": config.url_base_imagens} if config else {}


def atualizar_variacao_do_fornecedor(instancia, variacao):
    """Busca, normaliza e persiste somente a variação indicada.

    Os adapters atuais expõem apenas endpoints de catálogo completo. A rede
    pode portanto devolver o catálogo inteiro, mas apenas o produto-pai e a
    variação alvo são persistidos. Isso evita transformar a ação em uma
    sincronização silenciosa de todos os itens.
    """
    from apps.fornecedores.registry import obter_cliente
    from apps.fornecedores.management.commands.importar_fornecedor import Command

    fornecedor = variacao.produto.fornecedor
    checar_limite_diario_xbz(instancia, fornecedor)
    credencial = obter_credencial_ativa(instancia, fornecedor)
    cliente = obter_cliente(fornecedor, configuracao=obter_configuracao(fornecedor))
    normalizados = cliente.normalizar(cliente.buscar(credencial.credenciais))

    alvo = None
    for produto_normalizado in normalizados:
        for variacao_normalizada in produto_normalizado.variacoes:
            if variacao_normalizada.sku == variacao.sku:
                alvo = (produto_normalizado, variacao_normalizada)
                break
        if alvo:
            break
    if alvo is None:
        raise ValueError(
            f"A variação {variacao.sku!r} não foi encontrada no catálogo atual de {fornecedor}."
        )

    produto_normalizado, variacao_normalizada = alvo
    comando = Command()
    produto = comando._gravar_produto(
        instancia,
        fornecedor,
        produto_normalizado,
        reset_tiny_markers=False,
    )
    _resultado, atualizada = comando._gravar_variacao(produto, variacao_normalizada)
    return atualizada


_DEFAULT_INTERVALO_MINUTOS = 60


def listar_cadencias_com_defaults(instancia):
    """
    Uma linha por fornecedor (sempre as 4), mesmo que a instância ainda não
    tenha CadenciaFornecedor gravada para ele — usado tanto pelo endpoint
    GET /instancias/<slug>/cadencias/ quanto pelo detalhe da instância, para
    a tela sempre ter o que mostrar/editar sem um passo de "criar" separado.
    """
    existentes = {c.fornecedor: c for c in CadenciaFornecedor.objects.filter(instancia=instancia)}
    resultado = []
    for valor, _rotulo in Fornecedor.choices:
        cadencia = existentes.get(valor)
        if cadencia:
            resultado.append(
                {
                    "fornecedor": valor,
                    "intervalo_minutos": cadencia.intervalo_minutos,
                    "ativo": cadencia.ativo,
                    "propagar_tiny": cadencia.propagar_tiny,
                    "proxima_execucao_em": cadencia.proxima_execucao_em,
                }
            )
        else:
            resultado.append(
                {
                    "fornecedor": valor,
                    "intervalo_minutos": _DEFAULT_INTERVALO_MINUTOS,
                    "ativo": False,
                    "propagar_tiny": False,
                    "proxima_execucao_em": None,
                }
            )
    return resultado
