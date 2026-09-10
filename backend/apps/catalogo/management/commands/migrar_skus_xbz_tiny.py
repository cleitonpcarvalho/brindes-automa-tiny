"""Migra, sem recriar, os produtos XBZ que ainda usam CodigoXbz no Tiny."""

import json
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient, TinyRateLimitError

from ...models import StatusVariacao, Variacao
from ...tiny_dados_produto import DadosProdutoError, montar_payload_atualizacao
from ...tiny_sync import identidade_tiny, tiny_fornecedor_id_de


class Command(BaseCommand):
    help = "Migra os SKUs XBZ existentes no Tiny de CodigoXbz para CodigoComposto."

    # Quarenta chamadas/minuto no máximo antes mesmo de o Tiny informar seu
    # x-limit-api. Com quatro chamadas no pior caso, 4 mil itens levam várias
    # horas sem rajadas. O limiter Redis compartilhado continua valendo.
    INTERVALO_REQUISICOES = 1.5
    RATE_LIMIT_FALLBACK = 60
    MAX_TENTATIVAS_429 = 12
    TENTATIVAS_OPERACAO_429 = 3
    ESPERA_OPERACAO_429 = 60.0

    def add_arguments(self, parser):
        parser.add_argument("--instancia", required=True)
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument(
            "--sku",
            action="append",
            default=None,
            help="CodigoXbz específico; pode ser repetido para testar 2 ou 3 itens",
        )
        parser.add_argument("--dry-run", action="store_true", help="Padrão: GET e nenhuma escrita")
        parser.add_argument("--executar", action="store_true", help="Executa os PUTs")
        parser.add_argument("--mostrar-payload", action="store_true")
        parser.add_argument(
            "--intervalo-requisicoes",
            type=float,
            default=self.INTERVALO_REQUISICOES,
            help="Segundos mínimos entre chamadas ao Tiny (padrão: 1.5)",
        )
        parser.add_argument(
            "--max-tentativas-429",
            type=int,
            default=self.MAX_TENTATIVAS_429,
            help="Retentativas internas de cada chamada após HTTP 429 (padrão: 12)",
        )
        parser.add_argument(
            "--tentativas-operacao-429",
            type=int,
            default=self.TENTATIVAS_OPERACAO_429,
            help="Ciclos da operação após esgotar as retentativas internas (padrão: 3)",
        )
        parser.add_argument(
            "--espera-operacao-429",
            type=float,
            default=self.ESPERA_OPERACAO_429,
            help="Espera entre ciclos esgotados por 429 (padrão: 60s)",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["executar"]:
            raise CommandError("Passe --dry-run OU --executar, não os dois.")
        self._validar_opcoes(options)
        self._intervalo_requisicoes = options["intervalo_requisicoes"]
        self._tentativas_operacao_429 = options["tentativas_operacao_429"]
        self._espera_operacao_429 = options["espera_operacao_429"]
        self._ja_fez_requisicao = False

        executar = options["executar"]
        instancia = self._instancia(options["instancia"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")
        fornecedor_id = tiny_fornecedor_id_de(instancia, Fornecedor.XBZ)
        if not fornecedor_id:
            raise CommandError("Configure o ID do fornecedor XBZ no Tiny antes da migração.")

        fila = self._montar_fila(instancia, options)
        cliente = TinyApiClient(
            instancia,
            somente_leitura=not executar,
            max_tentativas_429=options["max_tentativas_429"],
            rate_limit_fallback=self.RATE_LIMIT_FALLBACK,
            sleep_fn=time.sleep,
            on_rate_limit=self._logar_429,
        )
        if not executar:
            self.stdout.write(
                self.style.WARNING(f"DRY-RUN — {len(fila)} item(ns), nenhum PUT será feito.")
            )

        cont = {
            "processados": 0,
            "atualizaveis": 0,
            "atualizados": 0,
            "ja_migrados": 0,
            "colisoes": 0,
            "ignorados": 0,
            "erros": 0,
        }
        for variacao in fila:
            cont["processados"] += 1
            rotulo = f"interno={variacao.sku!r} tiny_id={variacao.tiny_id}"
            put_enviado = False
            try:
                alvo = identidade_tiny(variacao)
                antes = self._chamar_tiny(
                    "validar Tiny ID", cliente.obter_produto, int(variacao.tiny_id)
                )
                atual = str(antes.get("sku") or "")
                if atual not in {variacao.sku, alvo}:
                    self._ignorar(rotulo, f"SKU atual inesperado no Tiny: {atual!r}", cont)
                    continue

                # Sempre valida colisão, inclusive no caminho JÁ MIGRADO. O
                # próprio tiny_id é permitido e torna a retomada idempotente.
                existente = self._chamar_tiny(
                    "validar colisão de SKU", cliente.buscar_produto_por_sku, alvo
                )
                if existente and str(existente.get("id")) != str(variacao.tiny_id):
                    cont["colisoes"] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"{rotulo}: COLISÃO — SKU Tiny {alvo!r} pertence ao "
                            f"id {existente.get('id')}"
                        )
                    )
                    continue

                # Se uma execução anterior chegou a aplicar o PUT, mas caiu
                # na confirmação, o GET acima já traz o estado real. Só pula
                # novo PUT quando todas as regras obrigatórias estão corretas.
                if atual == alvo and self._estado_ja_migrado(
                    antes, variacao, alvo, fornecedor_id
                ):
                    cont["ja_migrados"] += 1
                    if executar:
                        self._marcar_confirmada(variacao)
                    self.stdout.write(self.style.SUCCESS(f"{rotulo}: JÁ MIGRADO — tiny={alvo!r}"))
                    continue

                payload = montar_payload_atualizacao(
                    antes,
                    variacao=variacao,
                    tiny_fornecedor_id=fornecedor_id,
                    sku_atual_esperado=atual,
                )
                self._validar_payload_sem_imagens(payload)
                if options["mostrar_payload"]:
                    self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
                cont["atualizaveis"] += 1
                if not executar:
                    self.stdout.write(f"{rotulo}: SERIA ATUALIZADO para tiny={alvo!r}")
                    continue

                self._chamar_tiny(
                    "atualizar produto",
                    cliente.atualizar_produto,
                    int(variacao.tiny_id),
                    payload,
                )
                put_enviado = True
                depois = self._chamar_tiny(
                    "confirmar PUT", cliente.obter_produto, int(variacao.tiny_id)
                )
                self._confirmar(depois, variacao, alvo, fornecedor_id, antes=antes)
                self._marcar_confirmada(variacao)
                cont["atualizados"] += 1
                self.stdout.write(self.style.SUCCESS(f"{rotulo}: ATUALIZADO — tiny={alvo!r}"))
            except Exception as exc:
                cont["erros"] += 1
                contexto = (
                    "PUT enviado; confirmação inconclusiva"
                    if put_enviado
                    else "operação não concluída"
                )
                mensagem = f"{contexto}: {exc}"
                variacao.ultimo_erro = f"migrar_skus_xbz_tiny: {mensagem}"[:500]
                if executar:
                    variacao.save(update_fields=["ultimo_erro", "atualizado_em"])
                self.stderr.write(f"{rotulo}: ERRO — {mensagem}")

        self.stdout.write(self.style.SUCCESS(str(cont)))

    def _montar_fila(self, instancia, options):
        qs = (
            Variacao.objects.filter(
                produto__instancia=instancia,
                produto__fornecedor=Fornecedor.XBZ,
                status=StatusVariacao.CADASTRADO,
            )
            .exclude(tiny_id__isnull=True)
            .exclude(tiny_id="")
            .select_related("produto")
        )
        if options["sku"]:
            skus = [options["sku"]] if isinstance(options["sku"], str) else options["sku"]
            qs = qs.filter(sku__in=skus)
        qs = qs.order_by("id")
        if options["limite"]:
            qs = qs[: options["limite"]]
        return list(qs)

    def _chamar_tiny(self, descricao, funcao, *args):
        for ciclo in range(1, self._tentativas_operacao_429 + 1):
            if self._ja_fez_requisicao and self._intervalo_requisicoes:
                time.sleep(self._intervalo_requisicoes)
            self._ja_fez_requisicao = True
            try:
                return funcao(*args)
            except TinyRateLimitError:
                if ciclo >= self._tentativas_operacao_429:
                    raise
                self.stdout.write(
                    self.style.WARNING(
                        f"429 persistente ao {descricao}; aguardando "
                        f"{self._espera_operacao_429:g} segundos antes do ciclo "
                        f"{ciclo + 1}/{self._tentativas_operacao_429}."
                    )
                )
                time.sleep(self._espera_operacao_429)
        raise AssertionError("ciclo de retentativa 429 terminou sem resultado")

    def _logar_429(self, caminho, tentativa, espera, usou_retry_after):
        origem = "Retry-After" if usou_retry_after else "backoff"
        self.stdout.write(
            self.style.WARNING(
                f"429 em {caminho} (tentativa {tentativa}) — aguardando "
                f"{espera:g} segundos ({origem})."
            )
        )

    def _estado_ja_migrado(self, detalhe, variacao, alvo, fornecedor_id):
        try:
            self._confirmar(detalhe, variacao, alvo, fornecedor_id, antes=detalhe)
        except DadosProdutoError:
            return False
        return True

    def _confirmar(self, detalhe, variacao, alvo, fornecedor_id, *, antes):
        if str(detalhe.get("sku") or "") != alvo:
            raise DadosProdutoError("GET pós-PUT não confirmou o SKU composto")
        if detalhe.get("descricaoComplementar") != (variacao.produto.descricao or ""):
            raise DadosProdutoError("GET pós-PUT não confirmou a descrição complementar")
        precos = detalhe.get("precos") or {}
        if float(precos.get("preco") or 0) != 0 or float(
            precos.get("precoPromocional") or 0
        ) != 0:
            raise DadosProdutoError("GET pós-PUT não confirmou preço de venda zerado")
        if float(precos.get("precoCusto") or 0) != float(variacao.preco):
            raise DadosProdutoError("GET pós-PUT não confirmou preço de custo")
        fornecedores = detalhe.get("fornecedores") or []
        nosso = [f for f in fornecedores if str(f.get("id")) == str(fornecedor_id)]
        if not nosso or nosso[0].get("codigoProdutoNoFornecedor") != alvo:
            raise DadosProdutoError("GET pós-PUT não confirmou o código no fornecedor")

        for campo in ("descricao", "ncm", "dimensoes"):
            if campo in antes and antes.get(campo) != detalhe.get(campo):
                raise DadosProdutoError(f"GET pós-PUT detectou alteração inesperada em {campo}")
        if "estoque" in antes:
            campos_config = (
                "controlar",
                "sobEncomenda",
                "diasPreparacao",
                "localizacao",
                "minimo",
                "maximo",
            )
            for campo in campos_config:
                estoque_antes = antes.get("estoque") or {}
                estoque_depois = detalhe.get("estoque") or {}
                if campo in estoque_antes and estoque_antes.get(campo) != estoque_depois.get(
                    campo
                ):
                    raise DadosProdutoError(
                        f"GET pós-PUT detectou alteração inesperada em estoque.{campo}"
                    )
        if "anexos" in antes and antes.get("anexos") != detalhe.get("anexos"):
            raise DadosProdutoError("GET pós-PUT detectou alteração inesperada em anexos")

    def _validar_payload_sem_imagens(self, payload):
        if "anexos" in payload:
            raise DadosProdutoError("payload de migração contém anexos")

    def _marcar_confirmada(self, variacao):
        variacao.preco_custo_tiny_sincronizado = variacao.preco
        variacao.dados_tiny_sincronizados_em = timezone.now()
        variacao.ultimo_erro = ""
        variacao.save(
            update_fields=[
                "preco_custo_tiny_sincronizado",
                "dados_tiny_sincronizados_em",
                "ultimo_erro",
                "atualizado_em",
            ]
        )

    def _ignorar(self, rotulo, motivo, cont):
        cont["ignorados"] += 1
        self.stdout.write(self.style.WARNING(f"{rotulo}: IGNORADO — {motivo}"))

    def _validar_opcoes(self, options):
        if options["intervalo_requisicoes"] < 0:
            raise CommandError("--intervalo-requisicoes não pode ser negativo.")
        if options["max_tentativas_429"] < 1:
            raise CommandError("--max-tentativas-429 deve ser positivo.")
        if options["tentativas_operacao_429"] < 1:
            raise CommandError("--tentativas-operacao-429 deve ser positivo.")
        if options["espera_operacao_429"] < 0:
            raise CommandError("--espera-operacao-429 não pode ser negativa.")

    def _instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
