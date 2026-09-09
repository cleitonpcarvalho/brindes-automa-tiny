"""Migra, sem recriar, os produtos XBZ que ainda usam CodigoXbz no Tiny."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import StatusVariacao, Variacao
from ...tiny_dados_produto import DadosProdutoError, montar_payload_atualizacao
from ...tiny_sync import identidade_tiny, tiny_fornecedor_id_de


class Command(BaseCommand):
    help = "Migra os SKUs XBZ existentes no Tiny de CodigoXbz para CodigoComposto."

    def add_arguments(self, parser):
        parser.add_argument("--instancia", required=True)
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument("--sku", default=None, help="CodigoXbz de uma variação específica")
        parser.add_argument("--dry-run", action="store_true", help="Padrão: GET e nenhuma escrita")
        parser.add_argument("--executar", action="store_true", help="Executa os PUTs")
        parser.add_argument("--mostrar-payload", action="store_true")

    def handle(self, *args, **options):
        if options["dry_run"] and options["executar"]:
            raise CommandError("Passe --dry-run OU --executar, não os dois.")
        executar = options["executar"]
        instancia = self._instancia(options["instancia"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")
        fornecedor_id = tiny_fornecedor_id_de(instancia, Fornecedor.XBZ)
        if not fornecedor_id:
            raise CommandError("Configure o ID do fornecedor XBZ no Tiny antes da migração.")

        qs = Variacao.objects.filter(
            produto__instancia=instancia,
            produto__fornecedor=Fornecedor.XBZ,
            status=StatusVariacao.CADASTRADO,
        ).exclude(tiny_id__isnull=True).exclude(tiny_id="").select_related("produto")
        if options["sku"]:
            qs = qs.filter(sku=options["sku"])
        qs = qs.order_by("id")
        if options["limite"]:
            qs = qs[: options["limite"]]
        fila = list(qs)
        cliente = TinyApiClient(instancia, somente_leitura=not executar)
        if not executar:
            self.stdout.write(self.style.WARNING(f"DRY-RUN — {len(fila)} item(ns), nenhum PUT será feito."))

        cont = {"processados": 0, "atualizaveis": 0, "atualizados": 0, "ignorados": 0, "erros": 0}
        for variacao in fila:
            cont["processados"] += 1
            rotulo = f"interno={variacao.sku!r} tiny_id={variacao.tiny_id}"
            try:
                alvo = identidade_tiny(variacao)
                antes = cliente.obter_produto(int(variacao.tiny_id))
                atual = str(antes.get("sku") or "")
                if atual not in {variacao.sku, alvo}:
                    self._ignorar(rotulo, f"SKU atual inesperado no Tiny: {atual!r}", cont)
                    continue

                # Revalidação imediatamente antes do PUT. O próprio tiny_id é
                # permitido: isso torna a segunda execução idempotente.
                existente = cliente.buscar_produto_por_sku(alvo)
                if existente and str(existente.get("id")) != str(variacao.tiny_id):
                    self._ignorar(rotulo, f"colisão: SKU Tiny {alvo!r} pertence ao id {existente.get('id')}", cont)
                    continue

                payload = montar_payload_atualizacao(
                    antes,
                    variacao=variacao,
                    tiny_fornecedor_id=fornecedor_id,
                    sku_atual_esperado=atual,
                )
                if options["mostrar_payload"]:
                    self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
                cont["atualizaveis"] += 1
                if not executar:
                    self.stdout.write(f"{rotulo}: SERIA ATUALIZADO para tiny={alvo!r}")
                    continue

                cliente.atualizar_produto(int(variacao.tiny_id), payload)
                depois = cliente.obter_produto(int(variacao.tiny_id))
                self._confirmar(depois, variacao, alvo, fornecedor_id)
                variacao.preco_custo_tiny_sincronizado = variacao.preco
                variacao.dados_tiny_sincronizados_em = timezone.now()
                variacao.ultimo_erro = ""
                variacao.save(update_fields=[
                    "preco_custo_tiny_sincronizado",
                    "dados_tiny_sincronizados_em",
                    "ultimo_erro",
                    "atualizado_em",
                ])
                cont["atualizados"] += 1
                self.stdout.write(self.style.SUCCESS(f"{rotulo}: atualizado para tiny={alvo!r}"))
            except Exception as exc:
                cont["erros"] += 1
                variacao.ultimo_erro = f"migrar_skus_xbz_tiny: {exc}"[:500]
                if executar:
                    variacao.save(update_fields=["ultimo_erro", "atualizado_em"])
                self.stderr.write(f"{rotulo}: ERRO — {exc}")

        self.stdout.write(self.style.SUCCESS(str(cont)))

    def _confirmar(self, detalhe, variacao, alvo, fornecedor_id):
        if str(detalhe.get("sku") or "") != alvo:
            raise DadosProdutoError("GET pós-PUT não confirmou o SKU composto")
        precos = detalhe.get("precos") or {}
        if float(precos.get("preco") or 0) != 0 or float(precos.get("precoPromocional") or 0) != 0:
            raise DadosProdutoError("GET pós-PUT não confirmou preço de venda zerado")
        if float(precos.get("precoCusto") or 0) != float(variacao.preco):
            raise DadosProdutoError("GET pós-PUT não confirmou preço de custo")
        fornecedores = detalhe.get("fornecedores") or []
        nosso = [f for f in fornecedores if str(f.get("id")) == str(fornecedor_id)]
        if not nosso or nosso[0].get("codigoProdutoNoFornecedor") != alvo:
            raise DadosProdutoError("GET pós-PUT não confirmou o código no fornecedor")

    def _ignorar(self, rotulo, motivo, cont):
        cont["ignorados"] += 1
        self.stdout.write(self.style.WARNING(f"{rotulo}: IGNORADO — {motivo}"))

    def _instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
