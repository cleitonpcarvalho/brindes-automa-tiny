from django.core.management.base import BaseCommand, CommandError

from apps.catalogo.models import Variacao
from apps.instancias.constants import Fornecedor

from ...services import obter_configuracao
from ...spot import imagens_spot_da_variacao


class Command(BaseCommand):
    """
    Reconstrói `Variacao.imagens` das variações da Spot a partir do
    `payload_bruto` JÁ salvo no banco (a linha de `optionalsComplete` de
    cada variação + o `payload_bruto` do produto-pai) e da
    `ConfiguracaoFornecedor.url_base_imagens` da Spot.

    Por que existe: configurar a URL base NÃO muda o hash do payload, então
    uma nova `importar_fornecedor` ignoraria as variações Spot já
    existentes (mesmo hash => "ignorado"). Este comando preenche as imagens
    dessas variações sem depender de reimportação.

    Escopo do que é tocado: `Variacao.imagens`, o marcador de anexos
    `imagens_tiny_sincronizadas` (somente para remover URLs antigas) e
    `atualizado_em`. O `save()` roda com `update_fields` restrito — status,
    estoque, preço, NCM, cor, `tiny_id`, `hash_conteudo`, `payload_bruto` e
    qualquer outro campo ficam exatamente como estavam.

    Opções:
      --dry-run           não grava nada, só relata o que mudaria;
      --instancia <slug>  limita a uma instância (padrão: todas);
      --limite <n>        processa no máximo n variações.
    """

    help = "Backfill de Variacao.imagens das variações Spot a partir do payload_bruto salvo."

    def add_arguments(self, parser):
        parser.add_argument("--instancia", default=None, help="slug da instância (padrão: todas).")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limite", type=int, default=None)

    def handle(self, *args, **options):
        url_base = obter_configuracao(Fornecedor.SPOT).get("url_base_imagens", "")
        if not url_base:
            raise CommandError(
                "ConfiguracaoFornecedor.url_base_imagens para 'spot' está vazio — "
                "aplique a migration 0007_corrige_url_spot_oficial (ou configure "
                "a URL base no admin) antes de rodar o backfill."
            )

        dry_run = options["dry_run"]
        w = self.stdout.write
        if dry_run:
            w(self.style.WARNING("DRY-RUN — nenhuma alteração será gravada."))

        fila = (
            Variacao.objects.filter(produto__fornecedor=Fornecedor.SPOT)
            .select_related("produto")
            .order_by("produto_id", "sku", "id")
        )
        if options["instancia"]:
            fila = fila.filter(produto__instancia__slug=options["instancia"])
        if options["limite"]:
            fila = fila[: options["limite"]]

        analisadas = corretas = corrigiveis = corrigidas = sem_imagem = nao_reconhecidas = erros = 0
        for variacao in fila:
            analisadas += 1
            try:
                opcional = variacao.payload_bruto or {}
                produto_bruto = variacao.produto.payload_bruto or {}
                if not opcional:
                    nao_reconhecidas += 1
                    w(f"{variacao.sku}: sem payload_bruto salvo — não reconhecido")
                    continue

                novas = imagens_spot_da_variacao(opcional, produto_bruto, url_base)
                atuais = list(variacao.imagens or [])
                if not novas:
                    sem_imagem += 1
                    continue
                if novas == atuais:
                    corretas += 1
                    continue

                corrigiveis += 1
                w(f"[instancia {variacao.produto.instancia_id}] {variacao.sku}: "
                  f"{len(atuais)} -> {len(novas)} imagem(ns)")
                if not dry_run:
                    # Remove do marcador local URLs que deixaram de ser as
                    # URLs desejadas. O fluxo específico de anexos do Tiny
                    # reenviará somente quando for executado posteriormente.
                    marcadores = [
                        url for url in (variacao.imagens_tiny_sincronizadas or [])
                        if url in novas
                    ]
                    variacao.imagens = novas
                    variacao.imagens_tiny_sincronizadas = marcadores
                    variacao.save(update_fields=[
                        "imagens", "imagens_tiny_sincronizadas", "atualizado_em"
                    ])
                    corrigidas += 1
            except Exception as exc:
                erros += 1
                w(self.style.ERROR(f"{variacao.sku}: erro no backfill — {exc}"))
                continue

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if dry_run else ''}"
            f"Variações analisadas: {analisadas} | URLs já corretas: {corretas} | "
            f"URLs corrigíveis: {corrigiveis} | URLs corrigidas: {corrigidas} | "
            f"sem imagem: {sem_imagem} | casos não reconhecidos: {nao_reconhecidas} | "
            f"erros: {erros}"
        ))
