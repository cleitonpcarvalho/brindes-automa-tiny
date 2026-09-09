"""
Suporte para UM teste canário manual de `PUT /produtos/{id}` no Tiny.

NÃO é o backfill em lote (isso é `corrigir_dados_produto_tiny`). Roda para um
único produto, monta o mesmo payload DEFENSIVO da regra definitiva
(`apps.catalogo.tiny_dados_produto.montar_payload_atualizacao`) e:

Sem `--executar`: só GET + monta e imprime o payload que SERIA enviado.
Com `--executar`: GET antes -> PUT -> GET depois -> diff campo a campo.

A regra definitiva (cliente, 2026-09-08) altera só: descricaoComplementar
(= Produto.descricao), precos (preco=0, precoPromocional=0, precoCusto=preco
do fornecedor) e fornecedores (mesclado). Todo o resto do GET é preservado.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import Variacao
from ...tiny_dados_produto import comparar_campos, montar_payload_atualizacao
from ...tiny_sync import identidade_tiny
from ...tiny_sync import tiny_fornecedor_id_de


class Command(BaseCommand):
    help = (
        "Teste canário de PUT /produtos/{id} no Tiny para UM produto: sem --executar "
        "só monta e imprime o payload; com --executar faz GET -> PUT -> GET e imprime "
        "o diff campo a campo (regra definitiva: descricaoComplementar, precos, fornecedores)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--instancia", required=True, help="slug da Instancia")
        parser.add_argument("--tiny-id", required=True, type=int, help="id do produto no Tiny")
        parser.add_argument("--sku", required=True, help="SKU do produto (conferido contra o GET)")
        parser.add_argument("--fornecedor", required=True, choices=[f.value for f in Fornecedor])
        parser.add_argument(
            "--executar",
            action="store_true",
            help="Sem esta flag: só GET + payload (nenhum PUT). Com ela: GET -> PUT -> GET + diff.",
        )

    def handle(self, *args, **options):
        w = self.stdout.write
        executar = options["executar"]
        sku = options["sku"]
        tiny_id = options["tiny_id"]
        fornecedor = options["fornecedor"]

        instancia = self._obter_instancia(options["instancia"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        tiny_fornecedor_id = tiny_fornecedor_id_de(instancia, fornecedor)
        if not tiny_fornecedor_id:
            raise CommandError(
                f"Sem 'ID do fornecedor no Tiny' configurado para {fornecedor} nesta instância "
                "(Instância › Fornecedores). Configure antes de rodar o canário."
            )

        variacao = (
            Variacao.objects.select_related("produto")
            .filter(produto__instancia=instancia, produto__fornecedor=fornecedor, sku=sku)
            .first()
        )
        if variacao is None:
            raise CommandError(
                f"SKU {sku!r} não encontrado no espelho para o fornecedor {fornecedor} desta instância."
            )
        if not (variacao.produto.descricao or "").strip():
            w(self.style.WARNING(
                f"Produto.descricao do espelho está VAZIO para {sku!r} — o PUT enviaria "
                "descricaoComplementar em branco. Confira o espelho antes de --executar."
            ))

        cliente = TinyApiClient(instancia, somente_leitura=not executar)

        antes = cliente.obter_produto(tiny_id)
        sku_no_tiny = str(antes.get("sku") or "")
        identidade = identidade_tiny(variacao)
        if sku_no_tiny not in {sku, identidade}:
            raise CommandError(
                f"O produto tiny_id={tiny_id} tem sku={sku_no_tiny!r}, esperado {sku!r} ou {identidade!r} — "
                "abortado por segurança (produto errado)."
            )

        payload = montar_payload_atualizacao(
            antes, variacao=variacao, tiny_fornecedor_id=tiny_fornecedor_id,
            sku_atual_esperado=sku_no_tiny,
        )

        w("")
        w(self.style.MIGRATE_HEADING(
            f"Payload que {'SERÁ' if executar else 'SERIA'} enviado ao PUT /produtos/{tiny_id}:"
        ))
        w(json.dumps(payload, ensure_ascii=False, indent=2))
        w("")
        w(f"  fornecedores atuais no Tiny: {antes.get('fornecedores') or []}")
        w(f"  fornecedores no payload ...: {payload['fornecedores']}")

        if not executar:
            w("")
            w(self.style.WARNING("DRY-RUN — nenhum PUT foi feito. Rode de novo com --executar para aplicar."))
            return

        cliente.atualizar_produto(tiny_id, payload)
        w("")
        w(self.style.SUCCESS("PUT enviado (HTTP 204 = sucesso)."))

        depois = cliente.obter_produto(tiny_id)
        self._imprimir_diff(comparar_campos(antes, depois))

    # -- saída ----------------------------------------------------------

    def _imprimir_diff(self, linhas):
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING("Diff campo a campo (GET antes -> GET depois):"))
        inesperados = 0
        esperados_sem_mudanca = []
        for linha in linhas:
            campo = linha["campo"]
            if linha["igual"]:
                w(f"  =  {campo:<22} inalterado")
                if linha["esperado_mudar"]:
                    esperados_sem_mudanca.append(campo)
                continue
            if linha["esperado_mudar"]:
                w(self.style.SUCCESS(f"  ~  {campo:<22} alterado (esperado)"))
            else:
                inesperados += 1
                w(self.style.ERROR(f"  !! {campo:<22} ALTERADO — INESPERADO"))
            w(f"       antes : {json.dumps(linha['antes'], ensure_ascii=False, default=str)}")
            w(f"       depois: {json.dumps(linha['depois'], ensure_ascii=False, default=str)}")

        w("")
        if inesperados:
            w(self.style.ERROR(
                f"{inesperados} campo(s) mudaram sem ser esperado — NÃO seguir para o lote; "
                "revisar a montagem do payload e a semântica do PUT."
            ))
        else:
            w(self.style.SUCCESS(
                "Nenhuma alteração inesperada — só descricaoComplementar/precos/fornecedores mudaram."
            ))
        for campo in esperados_sem_mudanca:
            w(self.style.WARNING(f"Atenção: {campo!r} era esperado mudar e ficou igual — verificar."))

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
