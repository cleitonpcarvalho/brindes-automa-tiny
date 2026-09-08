"""
Backfill da REGRA DEFINITIVA de dados do produto no Tiny para produtos JÁ
CADASTRADOS (confirmada pelo cliente em 2026-09-08). Substitui e amplia o
antigo `sincronizar_preco_tiny` (que escrevia o custo como preço de venda —
comportamento agora incorreto, e o endpoint `PUT /produtos/{id}/preco` não
aceita `precoCusto`).

Para cada `Variacao` já cadastrada de UM fornecedor de UMA instância:
  GET /produtos/{tiny_id}  ->  monta payload DEFENSIVO  ->  PUT /produtos/{tiny_id}

O PUT altera SOMENTE (regra definitiva):
  descricaoComplementar = Produto.descricao do espelho
  precos.precoCusto      = Variacao.preco (valor do fornecedor)
  precos.preco           = 0   (venda sempre zerada)
  precos.precoPromocional = 0
  fornecedores           = fornecedor Tiny configurado do par, PRESERVANDO os
                           já existentes (nunca duplica; ver montar_fornecedores)

Todos os demais campos graváveis retornados pelo GET são reenviados como
estão. NUNCA toca em anexos (imagens) nem em `estoque.quantidade` (saldo).

Proteções:
  - exige `tiny_id` (não cria produto novo; não é a fila de cadastro);
  - confere o SKU do GET contra o do espelho — sem fuzzy; divergiu -> ignora;
  - só o fornecedor informado em --fornecedor;
  - idempotente/retomável pelo marcador `Variacao.dados_tiny_sincronizados_em`
    (+ `preco_custo_tiny_sincronizado`): reexecução pega só o que falta ou o
    custo que mudou depois;
  - erro num produto NÃO para o lote;
  - respeita o rate limiter compartilhado (via TinyApiClient).

`--dry-run` (padrão): GET + monta o payload, NÃO faz PUT.
`--executar`: aplica o PUT e avança os marcadores.
`--sku`: processa exatamente esse SKU (ignora os marcadores — retry manual).
`--verificar` (só com --executar): GET depois de cada PUT e imprime o diff.
"""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q
from django.utils import timezone

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import StatusVariacao, Variacao
from ...tiny_dados_produto import (
    DadosProdutoError,
    comparar_campos,
    montar_payload_atualizacao,
)
from ...tiny_sync import tiny_fornecedor_id_de


class Command(BaseCommand):
    help = (
        "Backfill da regra definitiva (descricaoComplementar/precoCusto/preco=0/fornecedor) "
        "nos produtos JÁ cadastrados no Tiny de um fornecedor. Padrão: dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--instancia", required=True, help="slug da Instancia")
        parser.add_argument("--fornecedor", required=True, choices=[f.value for f in Fornecedor])
        parser.add_argument("--sku", default=None, help="processa só este SKU (ignora os marcadores)")
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true", help="(padrão) GET + payload, sem PUT")
        parser.add_argument("--executar", action="store_true", help="aplica o PUT")
        parser.add_argument(
            "--verificar",
            action="store_true",
            help="só com --executar: GET depois de cada PUT e imprime o diff campo a campo",
        )

    def handle(self, *args, **options):
        w = self.stdout.write
        if options["dry_run"] and options["executar"]:
            raise CommandError("Passe --dry-run OU --executar, não os dois.")
        executar = options["executar"]
        fornecedor = options["fornecedor"]

        instancia = self._obter_instancia(options["instancia"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        # Resolvido UMA vez (nunca por SKU).
        tiny_fornecedor_id = tiny_fornecedor_id_de(instancia, fornecedor)
        if not tiny_fornecedor_id:
            raise CommandError(
                f"Sem 'ID do fornecedor no Tiny' configurado para {fornecedor} nesta instância "
                "(Instância › Fornecedores). Configure antes do backfill."
            )

        fila = self._montar_fila(instancia, fornecedor, options)
        if not fila:
            w(self.style.SUCCESS("Nada a corrigir — fila vazia."))
            return

        cliente = TinyApiClient(instancia, somente_leitura=not executar)
        if not executar:
            w(self.style.WARNING(f"DRY-RUN — {len(fila)} produto(s) na fila, nenhum PUT será feito."))

        processados = atualizados = ignorados = erros = 0
        for variacao in fila:
            processados += 1
            rotulo = f"[{fornecedor}] {variacao.sku!r} (tiny_id={variacao.tiny_id})"

            if not (variacao.tiny_id or "").strip():
                ignorados += 1
                w(self.style.WARNING(f"{rotulo}: IGNORADO — sem tiny_id confirmado."))
                continue

            try:
                antes = cliente.obter_produto(int(variacao.tiny_id))
            except Exception as exc:
                erros += 1
                self._registrar_erro(variacao, f"GET falhou: {exc}")
                self.stderr.write(f"{rotulo}: ERRO no GET — {exc}")
                continue

            sku_no_tiny = str(antes.get("sku") or "")
            if sku_no_tiny != variacao.sku:
                ignorados += 1
                w(self.style.WARNING(
                    f"{rotulo}: IGNORADO — o produto no Tiny tem sku={sku_no_tiny!r} (sem fuzzy)."
                ))
                continue

            try:
                payload = montar_payload_atualizacao(
                    antes, variacao=variacao, tiny_fornecedor_id=tiny_fornecedor_id
                )
            except DadosProdutoError as exc:
                erros += 1
                self._registrar_erro(variacao, str(exc))
                self.stderr.write(f"{rotulo}: ERRO ao montar payload — {exc}")
                continue

            if not executar:
                atualizados += 1  # "seria atualizado"
                w(f"{rotulo}: SERIA ATUALIZADO")
                w("  " + json.dumps(payload, ensure_ascii=False, indent=2).replace("\n", "\n  "))
                continue

            try:
                cliente.atualizar_produto(int(variacao.tiny_id), payload)
            except Exception as exc:  # uma variação ruim não pode travar o lote
                erros += 1
                self._registrar_erro(variacao, f"PUT falhou: {exc}")
                self.stderr.write(f"{rotulo}: ERRO no PUT — {exc}")
                continue

            variacao.preco_custo_tiny_sincronizado = variacao.preco
            variacao.dados_tiny_sincronizados_em = timezone.now()
            variacao.ultimo_erro = ""
            variacao.save(update_fields=[
                "preco_custo_tiny_sincronizado",
                "dados_tiny_sincronizados_em",
                "ultimo_erro",
                "atualizado_em",
            ])
            atualizados += 1
            w(self.style.SUCCESS(f"{rotulo}: ATUALIZADO"))

            if options["verificar"]:
                self._imprimir_diff(cliente.obter_produto(int(variacao.tiny_id)), antes)

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if not executar else ''}"
            f"processados: {processados} | atualizados: {atualizados} | "
            f"ignorados: {ignorados} | erros: {erros}"
        ))

    # -- fila ----------------------------------------------------------

    def _montar_fila(self, instancia, fornecedor, options):
        base = (
            Variacao.objects.filter(
                produto__instancia=instancia,
                produto__fornecedor=fornecedor,
                status=StatusVariacao.CADASTRADO,
            )
            .select_related("produto")
        )
        if options["sku"]:
            # retry manual de UM sku — ignora os marcadores.
            fila = base.filter(sku=options["sku"])
        else:
            base = base.exclude(tiny_id__isnull=True).exclude(tiny_id="")
            nao_corrigido = (
                Q(dados_tiny_sincronizados_em__isnull=True)
                | Q(preco_custo_tiny_sincronizado__isnull=True)
                | ~Q(preco=F("preco_custo_tiny_sincronizado"))  # custo mudou desde a correção
            )
            fila = base.filter(nao_corrigido)
        fila = fila.order_by("produto__codigo_pai", "sku", "id")
        if options["limite"]:
            fila = fila[: options["limite"]]
        return list(fila)

    # -- saída -------------------------------------------------------

    def _imprimir_diff(self, depois, antes):
        w = self.stdout.write
        for linha in comparar_campos(antes, depois):
            if linha["igual"]:
                continue
            marca = "  ~ " if linha["esperado_mudar"] else "  !! INESPERADO "
            w(f"{marca}{linha['campo']}: {linha['antes']!r} -> {linha['depois']!r}")

    def _registrar_erro(self, variacao, mensagem):
        variacao.ultimo_erro = f"corrigir_dados_produto_tiny: {mensagem}"[:500]
        variacao.save(update_fields=["ultimo_erro", "atualizado_em"])

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
