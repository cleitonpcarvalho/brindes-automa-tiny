"""
Espelho local (somente leitura) do catálogo de produtos que já existe no
Tiny de uma instância.

Lê `GET /produtos` (paginado) e, para os campos que a listagem não traz,
`GET /produtos/{id}`. NUNCA chama POST/PUT/PATCH/DELETE no Tiny — não cria,
não atualiza e não exclui nada lá. Grava/atualiza `catalogo.ProdutoTiny`
por upsert idempotente (chave `instancia` + `tiny_id`, comparação por
`hash_conteudo`). É retomável: rodar de novo continua de onde parou e pula
o que não mudou.

Não faz matching/deduplicação com Produto/Variacao dos fornecedores —
isso é um passo futuro.
"""

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import ProdutoTiny, calcular_hash_conteudo

PAGE_SIZE_PADRAO = 100  # default documentado da API v3
INTERVALO_REFRESH_TOKEN = 100  # a cada N produtos, recarrega o access_token do banco


def _dec(valor):
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = (
        "Espelha localmente (ProdutoTiny) o catálogo de produtos que já existe no "
        "Tiny da instância. Somente leitura — nunca escreve no Tiny."
    )

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug", help="slug da Instancia")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Consulta a API e mostra estatísticas, mas NÃO grava nenhum ProdutoTiny.",
        )
        parser.add_argument(
            "--sem-detalhe",
            action="store_true",
            help="Não faz chamadas a GET /produtos/{id} — espelha só os campos da "
            "listagem (id, sku, descricao, tipo, situacao, unidade, gtin, precos). "
            "ncm/origem/marca/dimensões ficam em branco. Prévia rápida: ~21 chamadas.",
        )
        parser.add_argument(
            "--limite",
            type=int,
            default=None,
            help="Processa no máximo N produtos nesta execução (o resto fica para a próxima).",
        )
        parser.add_argument(
            "--situacao",
            choices=["A", "I", "E"],
            default=None,
            help="Filtra pela situação no Tiny: A (ativo), I (inativo), E (excluído). Padrão: todos.",
        )
        parser.add_argument(
            "--page-size", type=int, default=PAGE_SIZE_PADRAO, help="Tamanho da página da listagem."
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        cliente = TinyApiClient(instancia)
        dry_run = options["dry_run"]

        itens, chamadas_listagem, total_tiny = self._listar_tudo(
            cliente, page_size=options["page_size"], situacao=options["situacao"]
        )
        if options["limite"] is not None:
            itens = itens[: options["limite"]]

        stats = {
            "total_no_tiny": total_tiny,
            "processados": 0,
            "novos": 0,
            "atualizados": 0,
            "inalterados": 0,
            "com_detalhe": 0,
            "sem_detalhe": 0,
            "situacao_A": 0,
            "situacao_I": 0,
            "situacao_E": 0,
            "situacao_outra": 0,
            "com_gtin": 0,
            "com_ncm": 0,
            "com_sku": 0,
            "chamadas_listagem": chamadas_listagem,
            "chamadas_detalhe": 0,
        }

        for indice, item in enumerate(itens):
            if indice and indice % INTERVALO_REFRESH_TOKEN == 0:
                # Carga longa: o beat pode ter renovado o token no meio. O
                # client lê self.instancia.access_token a cada request, então
                # basta recarregar o objeto in-place.
                instancia.refresh_from_db(fields=["access_token", "rate_limit_por_minuto"])

            self._processar_item(cliente, instancia, item, options, dry_run, stats)

        self._imprimir_resumo(instancia, dry_run, stats)

    # -- listagem paginada ------------------------------------------------

    def _listar_tudo(self, cliente, *, page_size, situacao):
        itens = []
        chamadas = 0
        offset = 0
        total = 0
        while True:
            corpo = cliente.listar_produtos(limit=page_size, offset=offset, situacao=situacao)
            chamadas += 1
            pagina = corpo.get("itens") or []
            total = (corpo.get("paginacao") or {}).get("total", total)
            itens.extend(pagina)
            offset += page_size
            if not pagina or offset >= total:
                break
        return itens, chamadas, total

    # -- por produto ----------------------------------------------------

    def _processar_item(self, cliente, instancia, item, options, dry_run, stats):
        tiny_id = item.get("id")
        if tiny_id is None:
            return

        existente = ProdutoTiny.objects.filter(instancia=instancia, tiny_id=tiny_id).first()
        detalhe_reusavel = (existente.payload_bruto or {}).get("detalhe") if (existente and existente.tem_detalhe) else None
        data_alteracao_atual = str(item.get("dataAlteracao") or "")

        if options["sem_detalhe"]:
            detalhe = detalhe_reusavel  # nunca busca; preserva o que já tinha
        elif (
            detalhe_reusavel is not None
            and existente.data_alteracao_tiny
            and existente.data_alteracao_tiny == data_alteracao_atual
        ):
            detalhe = detalhe_reusavel  # nada mudou desde a última passada → pula o GET /produtos/{id}
        else:
            detalhe = cliente.obter_produto(tiny_id)
            stats["chamadas_detalhe"] += 1

        payload = {"listagem": item, "detalhe": detalhe}
        hash_novo = calcular_hash_conteudo(payload)

        stats["processados"] += 1
        self._contar_atributos(item, detalhe, stats)
        stats["com_detalhe" if detalhe is not None else "sem_detalhe"] += 1

        if existente and existente.hash_conteudo == hash_novo:
            stats["inalterados"] += 1
            return

        resultado = "atualizados" if existente else "novos"
        stats[resultado] += 1

        if dry_run:
            return

        campos = self._montar_campos(item, detalhe)
        campos.update(
            payload_bruto=payload,
            tem_detalhe=detalhe is not None,
            sincronizado_em=timezone.now(),
        )
        ProdutoTiny.objects.update_or_create(
            instancia=instancia, tiny_id=tiny_id, defaults=campos
        )

    @staticmethod
    def _contar_atributos(item, detalhe, stats):
        situacao = item.get("situacao") or (detalhe or {}).get("situacao") or ""
        chave = f"situacao_{situacao}" if situacao in ("A", "I", "E") else "situacao_outra"
        stats[chave] += 1
        if str(item.get("gtin") or (detalhe or {}).get("gtin") or "").strip():
            stats["com_gtin"] += 1
        if str((detalhe or {}).get("ncm") or "").strip():
            stats["com_ncm"] += 1
        if str(item.get("sku") or "").strip():
            stats["com_sku"] += 1

    @staticmethod
    def _montar_campos(item, detalhe):
        d = detalhe or {}
        precos_l = item.get("precos") or {}
        precos_d = d.get("precos") or {}
        dim = d.get("dimensoes") or {}
        marca = d.get("marca") or {}
        cat = d.get("categoria") or {}
        estoque_d = d.get("estoque") or {}

        def preco(chave):
            return _dec(precos_d.get(chave, precos_l.get(chave)))

        return {
            "sku": item.get("sku") or "",
            "descricao": item.get("descricao") or d.get("descricao") or "",
            "descricao_complementar": d.get("descricaoComplementar") or "",
            "tipo": item.get("tipo") or d.get("tipo") or "",
            "situacao": item.get("situacao") or d.get("situacao") or "",
            "tipo_variacao": item.get("tipoVariacao") or "",
            "gtin": str(item.get("gtin") or d.get("gtin") or ""),
            "ncm": d.get("ncm") or "",
            "unidade": item.get("unidade") or d.get("unidade") or "",
            "origem": str(d.get("origem") or ""),
            "marca": marca.get("nome") or "",
            "marca_id": marca.get("id"),
            "categoria": cat.get("caminhoCompleto") or cat.get("nome") or "",
            "categoria_id": cat.get("id"),
            "preco": preco("preco"),
            "preco_promocional": preco("precoPromocional"),
            "preco_custo": preco("precoCusto"),
            "largura": dim.get("largura"),
            "altura": dim.get("altura"),
            "comprimento": dim.get("comprimento"),
            "diametro": dim.get("diametro"),
            "peso_liquido": dim.get("pesoLiquido"),
            "peso_bruto": dim.get("pesoBruto"),
            "estoque_quantidade": estoque_d.get("quantidade"),
            "data_criacao_tiny": str(item.get("dataCriacao") or ""),
            "data_alteracao_tiny": str(item.get("dataAlteracao") or ""),
        }

    # -- saída ---------------------------------------------------------

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None

    def _imprimir_resumo(self, instancia, dry_run, stats):
        w = self.stdout.write
        if dry_run:
            w(self.style.WARNING("DRY-RUN — nenhum ProdutoTiny foi gravado."))
        w("")
        w(f"  Instância .................. {instancia.slug}")
        w(f"  Produtos no Tiny (total) .. {stats['total_no_tiny']}")
        w(f"  Processados nesta execução  {stats['processados']}")
        w(f"    novos ................... {stats['novos']}")
        w(f"    atualizados ............. {stats['atualizados']}")
        w(f"    inalterados ............. {stats['inalterados']}")
        w(f"  Com detalhe / sem detalhe . {stats['com_detalhe']} / {stats['sem_detalhe']}")
        w(f"  Situação A / I / E / outra . {stats['situacao_A']} / {stats['situacao_I']} / {stats['situacao_E']} / {stats['situacao_outra']}")
        w(f"  Com SKU ................... {stats['com_sku']}")
        w(f"  Com GTIN .................. {stats['com_gtin']}")
        w(f"  Com NCM (do detalhe) ..... {stats['com_ncm']}")
        w("")
        w(f"  Chamadas à API — listagem . {stats['chamadas_listagem']}")
        w(f"  Chamadas à API — detalhe .. {stats['chamadas_detalhe']}")
        w(f"  Chamadas à API — total .... {stats['chamadas_listagem'] + stats['chamadas_detalhe']}")
