from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalogo.models import Produto, Variacao, calcular_hash_conteudo
from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.sincronizacao.models import (
    Execucao,
    LogItem,
    NivelLog,
    StatusExecucao,
    TipoExecucao,
)

from ...registry import obter_cliente
from ...services import checar_limite_diario_xbz, obter_configuracao, obter_credencial_ativa


class Command(BaseCommand):
    help = (
        "Busca o catálogo de um fornecedor para uma instância, normaliza e grava no "
        "espelho local (Produto/Variacao). Não escreve nada no Tiny."
    )

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug", help="slug da Instancia")
        parser.add_argument("fornecedor", choices=[f.value for f in Fornecedor])
        parser.add_argument(
            "--tipo",
            choices=[t.value for t in TipoExecucao],
            default=TipoExecucao.INCREMENTAL,
            help="tipo da execução registrada (padrão: incremental).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="ignora a checagem de 'já importei esse fornecedor hoje' (relevante para a "
            "xbz, que tem limite de 24 chamadas/dia).",
        )
        parser.add_argument(
            "--execucao-id",
            type=int,
            default=None,
            help="reusa uma Execucao já criada (passo 10: sincronização manual via API, que "
            "precisa devolver o id da execução antes de enfileirar) em vez de criar uma nova "
            "e pula as checagens de limite diário/credencial — quem criou a Execucao já as fez.",
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        fornecedor = options["fornecedor"]
        execucao_id = options["execucao_id"]

        if execucao_id is None:
            self._checar_limite_diario(instancia, fornecedor, options["force"])
            credencial = self._obter_credencial(instancia, fornecedor)
            execucao = Execucao.objects.create(
                instancia=instancia, fornecedor=fornecedor, tipo=options["tipo"]
            )
        else:
            execucao = self._obter_execucao(execucao_id)
            credencial = None  # buscada dentro do try — ver comentário abaixo

        try:
            if credencial is None:
                # Caminho da sincronização manual (passo 10): a view já validou
                # a credencial de forma síncrona antes de criar a Execucao e
                # enfileirar, mas entre o enqueue e esta chamada ela pode ter
                # sido desativada/removida (corrida rara) — nesse caso, cair no
                # `except Exception` abaixo e marcar a Execucao como falha é o
                # comportamento certo, em vez de deixá-la presa em "rodando".
                credencial = obter_credencial_ativa(instancia, fornecedor)

            configuracao = obter_configuracao(fornecedor)
            cliente = obter_cliente(fornecedor, configuracao=configuracao)

            payload_bruto = self._buscar(cliente, credencial, execucao)
            produtos_normalizados = self._normalizar(cliente, payload_bruto, execucao)

            totais = self._gravar(instancia, fornecedor, produtos_normalizados, execucao)

            execucao.finalizada_em = timezone.now()
            execucao.total_lidos = totais["lidos"]
            execucao.total_novos = totais["novos"]
            execucao.total_atualizados = totais["atualizados"]
            execucao.total_ignorados = totais["ignorados"]
            execucao.total_erros = totais["erros"]
            execucao.status = StatusExecucao.SUCESSO if totais["erros"] == 0 else StatusExecucao.PARCIAL
            execucao.save()
        except CommandError:
            raise
        except Exception as exc:
            # Qualquer falha não prevista nos pontos específicos abaixo (ex.:
            # erro ao gravar fora do loop de itens) não pode deixar a Execucao
            # presa em "rodando" para sempre — a sincronização manual (passo
            # 10) mostra esse status ao usuário em tempo real.
            self._falhar_execucao(execucao, "Falha inesperada na importação", exc)
            raise CommandError(str(exc)) from exc

        LogItem.objects.create(
            execucao=execucao,
            nivel=NivelLog.INFO,
            mensagem="Importação concluída",
            detalhe=totais,
        )

        self.stdout.write(self.style.SUCCESS(f"[{fornecedor}] {instancia}: {totais}"))

    # -- passos ---------------------------------------------------------

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None

    def _obter_execucao(self, execucao_id):
        try:
            return Execucao.objects.get(pk=execucao_id)
        except Execucao.DoesNotExist:
            raise CommandError(f"Execucao com id '{execucao_id}' não encontrada.") from None

    def _checar_limite_diario(self, instancia, fornecedor, force):
        try:
            checar_limite_diario_xbz(instancia, fornecedor, force=force)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def _obter_credencial(self, instancia, fornecedor):
        try:
            return obter_credencial_ativa(instancia, fornecedor)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def _buscar(self, cliente, credencial, execucao):
        try:
            return cliente.buscar(credencial.credenciais)
        except Exception as exc:
            self._falhar_execucao(execucao, "Falha ao buscar dados do fornecedor", exc)
            raise CommandError(str(exc)) from exc

    def _normalizar(self, cliente, payload_bruto, execucao):
        try:
            return cliente.normalizar(payload_bruto)
        except Exception as exc:
            self._falhar_execucao(execucao, "Falha ao normalizar payload do fornecedor", exc)
            raise CommandError(str(exc)) from exc

    def _falhar_execucao(self, execucao, mensagem, exc):
        execucao.status = StatusExecucao.FALHA
        execucao.mensagem_erro = str(exc)
        execucao.finalizada_em = timezone.now()
        execucao.save()
        LogItem.objects.create(
            execucao=execucao, nivel=NivelLog.ERRO, mensagem=mensagem, detalhe={"erro": str(exc)}
        )

    def _gravar(self, instancia, fornecedor, produtos_normalizados, execucao):
        totais = {"lidos": 0, "novos": 0, "atualizados": 0, "ignorados": 0, "erros": 0}

        for produto_normalizado in produtos_normalizados:
            try:
                produto = self._gravar_produto(instancia, fornecedor, produto_normalizado)
            except Exception as exc:
                totais["erros"] += 1
                LogItem.objects.create(
                    execucao=execucao,
                    nivel=NivelLog.ERRO,
                    mensagem=f"Falha ao gravar produto {produto_normalizado.codigo_pai}",
                    detalhe={"erro": str(exc)},
                )
                continue

            for variacao_normalizada in produto_normalizado.variacoes:
                totais["lidos"] += 1
                try:
                    resultado, variacao = self._gravar_variacao(produto, variacao_normalizada)
                    totais[resultado] += 1
                except Exception as exc:
                    totais["erros"] += 1
                    LogItem.objects.create(
                        execucao=execucao,
                        nivel=NivelLog.ERRO,
                        mensagem=f"Falha ao gravar variação {variacao_normalizada.sku}",
                        detalhe={"erro": str(exc)},
                    )

        return totais

    def _gravar_produto(self, instancia, fornecedor, produto_normalizado):
        produto, _ = Produto.objects.get_or_create(
            instancia=instancia,
            fornecedor=fornecedor,
            codigo_pai=produto_normalizado.codigo_pai,
            defaults={"nome": produto_normalizado.nome},
        )
        # Sempre atualiza os campos mutáveis, mesmo se o produto já existia —
        # Produto.save() reaplica a regra do prefixo "P@" (xbz) a cada chamada,
        # o que é seguro rodar de novo (idempotente).
        produto.nome = produto_normalizado.nome
        produto.descricao = produto_normalizado.descricao
        produto.categorias = produto_normalizado.categorias
        produto.imagens = produto_normalizado.imagens
        produto.atributos = produto_normalizado.atributos
        produto.atualizado_em_fornecedor = produto_normalizado.atualizado_em_fornecedor
        produto.payload_bruto = produto_normalizado.payload_bruto
        produto.save()
        return produto

    def _gravar_variacao(self, produto, variacao_normalizada):
        """
        Idempotência: se já existe uma Variacao com esse sku e o hash do
        payload bruto não mudou, não escreve nada e conta como 'ignorado' —
        em particular, um status já definido (ex.: 'cadastrado' por um passo
        futuro) não é tocado. Se mudou (ou é nova), grava os campos vindos
        do fornecedor; regra de estoque e regra de descontinuado continuam
        sendo aplicadas dentro de Variacao.save(), não aqui.
        """
        hash_novo = calcular_hash_conteudo(variacao_normalizada.payload_bruto)

        variacao = Variacao.objects.filter(produto=produto, sku=variacao_normalizada.sku).first()
        if variacao is not None and variacao.hash_conteudo == hash_novo:
            return "ignorados", variacao

        existia = variacao is not None
        if variacao is None:
            variacao = Variacao(produto=produto, sku=variacao_normalizada.sku)

        variacao.nome = variacao_normalizada.nome
        variacao.ncm = variacao_normalizada.ncm
        variacao.preco = variacao_normalizada.preco  # regra do cliente nº 4: sem margem
        variacao.estoque = variacao_normalizada.estoque
        variacao.cor = variacao_normalizada.cor
        variacao.tamanho = variacao_normalizada.tamanho
        variacao.capacidade = variacao_normalizada.capacidade
        variacao.largura = variacao_normalizada.dimensoes.largura
        variacao.altura = variacao_normalizada.dimensoes.altura
        variacao.comprimento = variacao_normalizada.dimensoes.comprimento
        variacao.diametro = variacao_normalizada.dimensoes.diametro
        variacao.peso_liquido = variacao_normalizada.dimensoes.peso_liquido
        variacao.peso_bruto = variacao_normalizada.dimensoes.peso_bruto
        variacao.imagens = variacao_normalizada.imagens
        variacao.atributos = variacao_normalizada.atributos
        variacao.payload_bruto = variacao_normalizada.payload_bruto
        variacao.save()

        return ("atualizados" if existia else "novos"), variacao
