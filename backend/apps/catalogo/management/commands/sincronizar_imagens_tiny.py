from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import StatusVariacao, Variacao
from .cadastrar_produtos_tiny import MAX_ANEXOS_POR_PRODUTO, imagens_utilizaveis


class Command(BaseCommand):
    """
    Replica no Tiny as imagens do fornecedor para produtos JÁ cadastrados
    (`status=cadastrado` com `tiny_id`), pelo endpoint específico
    `POST /produtos/{idProduto}/anexos`.

    O `POST /produtos` NÃO cria mais anexos (no 1º teste real, MC511, a
    imagem enviada na criação não apareceu no ERP). A sincronização de
    imagem é um passo separado, com o `tiny_id` confirmado.

    Regras:
      - só URLs REAIS do espelho (`Variacao.imagens`); nada de inventar
        (a Spot já vem sem imagem quando não há `url_base_imagens`);
      - no máximo MAX_ANEXOS_POR_PRODUTO (5) por produto;
      - ausência de imagem NÃO é erro — o produto simplesmente fica sem;
      - falha ao enviar imagem NÃO altera status nem `tiny_id` — só grava
        `ultimo_erro` e tenta de novo na próxima rodada.

    Idempotência: antes de qualquer POST, faz `GET /produtos/{id}` e só
    envia as URLs que ainda NÃO estão nos anexos do produto. Um marcador
    local (`Variacao.imagens_tiny_sincronizadas`) evita até o GET quando já
    se sabe que tudo foi sincronizado.

    `--dry-run`: nenhuma escrita no Tiny (o cliente levanta em qualquer
    POST) e nenhuma escrita local — só GET de diff e o que seria enviado.

    Seleção: `--fornecedor`, `--skus` (lista por vírgula), `--limite`.
    """

    help = "Sincroniza as imagens do fornecedor para o Tiny, via POST /produtos/{id}/anexos."

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug")
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--fornecedor", choices=[f.value for f in Fornecedor], default=None)
        parser.add_argument("--skus", default=None, help="Lista explícita de SKUs (por vírgula).")

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        dry_run = options["dry_run"]
        w = self.stdout.write
        if dry_run:
            w(self.style.WARNING("DRY-RUN — nenhuma escrita no Tiny e nenhuma alteração local."))

        fila = (
            Variacao.objects.filter(
                produto__instancia=instancia, status=StatusVariacao.CADASTRADO
            )
            .exclude(tiny_id__isnull=True)
            .exclude(tiny_id="")
            .exclude(imagens=[])
            .select_related("produto")
        )
        if options["fornecedor"]:
            fila = fila.filter(produto__fornecedor=options["fornecedor"])
        skus = [s.strip() for s in (options["skus"] or "").split(",") if s.strip()]
        if skus:
            fila = fila.filter(sku__in=skus)
        fila = fila.order_by("produto__fornecedor", "sku", "id")
        if options["limite"]:
            fila = fila[: options["limite"]]

        cliente = TinyApiClient(instancia, somente_leitura=dry_run)
        enviadas = ja_ok = sem_imagem = erros = 0

        for variacao in list(fila):
            rot = f"[{variacao.produto.fornecedor}] {variacao.sku!r} (tiny_id={variacao.tiny_id})"
            desejadas = imagens_utilizaveis(variacao)

            if not desejadas:
                sem_imagem += 1
                w(f"{rot}: sem imagem utilizável no espelho — mantém sem imagem")
                continue

            marcadas = set(variacao.imagens_tiny_sincronizadas or [])
            if set(desejadas).issubset(marcadas):
                ja_ok += 1
                w(f"{rot}: já sincronizado ({len(desejadas)} imagem(ns)) — pulado")
                continue

            try:
                atuais = cliente.anexos_do_produto(int(variacao.tiny_id))  # GET
            except Exception as exc:
                erros += 1
                self._registrar_erro(variacao, f"Falha ao consultar anexos: {exc}", dry_run)
                self.stderr.write(f"{rot}: erro ao consultar anexos: {exc}")
                continue

            faltando = [u for u in desejadas if u not in atuais]
            presentes = [u for u in desejadas if u in atuais]

            if not faltando:
                ja_ok += 1
                self._marcar_sincronizadas(variacao, presentes, dry_run)
                w(f"{rot}: {len(presentes)} imagem(ns) já no Tiny — só atualiza o marcador")
                continue

            w(f"{rot}: enviaria {len(faltando)} imagem(ns) nova(s) ({len(presentes)} já lá)")
            if dry_run:
                for u in faltando:
                    w(f"    + {u}")
                continue

            try:
                cliente.adicionar_anexos_produto(int(variacao.tiny_id), faltando)
                self._marcar_sincronizadas(variacao, presentes + faltando, dry_run)
                enviadas += 1
            except Exception as exc:  # NÃO perde o vínculo do produto já criado
                erros += 1
                self._registrar_erro(variacao, f"Falha ao enviar imagens: {exc}", dry_run)
                self.stderr.write(f"{rot}: erro ao enviar imagens: {exc}")

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if dry_run else ''}"
            f"Com imagem enviada: {enviadas} | já sincronizado: {ja_ok} | "
            f"sem imagem: {sem_imagem} | erros: {erros}"
        ))

    # -- persistência local -----------------------------------------

    @staticmethod
    def _marcar_sincronizadas(variacao, urls, dry_run):
        if dry_run:
            return
        variacao.imagens_tiny_sincronizadas = sorted(set(urls))[:MAX_ANEXOS_POR_PRODUTO]
        variacao.ultimo_erro = ""
        variacao.save(update_fields=["imagens_tiny_sincronizadas", "ultimo_erro", "atualizado_em"])

    @staticmethod
    def _registrar_erro(variacao, mensagem, dry_run):
        if dry_run:
            return
        variacao.ultimo_erro = mensagem
        variacao.save(update_fields=["ultimo_erro", "atualizado_em"])

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
