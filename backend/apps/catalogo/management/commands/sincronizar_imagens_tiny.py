from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import StatusVariacao, Variacao
from .cadastrar_produtos_tiny import MAX_ANEXOS_POR_PRODUTO, imagens_utilizaveis


class Command(BaseCommand):
    """
    Replica no Tiny as imagens do fornecedor para produtos JÁ cadastrados
    (`status=cadastrado` com `tiny_id`), pelo endpoint `PUT
    /produtos/{idProduto}/anexos`, enviando com `externo=false` (o Tiny
    BAIXA a imagem e a hospeda — confirmado no MC511; com `externo=true` a
    URL ficava registrada mas a imagem não aparecia no ERP).

    O `POST /produtos` NÃO manda mais anexos — a sincronização de imagem é
    um passo separado, com o `tiny_id` confirmado.

    Regras:
      - só URLs REAIS do espelho (`Variacao.imagens`); nada de inventar
        (a Spot já vem sem imagem quando não há `url_base_imagens`);
      - no máximo MAX_ANEXOS_POR_PRODUTO (5) por produto;
      - ausência de imagem NÃO é erro — o produto simplesmente fica sem;
      - falha ao sincronizar NÃO altera status nem `tiny_id` — só grava
        `ultimo_erro` e tenta de novo na próxima rodada.

    IDEMPOTÊNCIA — o marcador local é a fonte de verdade:
      `Variacao.imagens_tiny_sincronizadas` guarda as URLs ORIGINAIS do
      fornecedor já importadas com sucesso. Não dá para comparar essas URLs
      com o que o `GET /produtos/{id}` devolve, porque depois do
      `externo=false` o Tiny devolve a URL INTERNA dele (S3), diferente da
      original.
        1. marcador já cobre todas as URLs desejadas -> nada a fazer (sem GET);
        2. senão, GET dos anexos: se o Tiny já tem QUANTIDADE >= a desejada
           (produto já internalizado — ex.: MC511 corrigido à mão), NÃO
           reenvia, só reconcilia o marcador com as URLs originais;
        3. senão, PUT com a lista completa das URLs desejadas e marca todas
           como sincronizadas.
    Reexecução após sucesso não faz nenhuma escrita nem chamada.

    `--dry-run`: nenhuma escrita no Tiny (o cliente levanta em qualquer
    PUT/POST) e nenhuma escrita local — só o GET de diagnóstico.

    `--so-reconciliar`: NUNCA chama o endpoint de anexos. Só faz o GET e,
    para os produtos que o Tiny já tem (contagem >= desejada), grava o
    marcador local com as URLs originais. Serve para o caso MC511 (imagem
    já lá, marcador ausente) sem risco de duplicar.

    Seleção: `--fornecedor`, `--skus` (lista por vírgula), `--limite`.
    """

    help = "Sincroniza as imagens do fornecedor para o Tiny, via PUT /produtos/{id}/anexos (externo=false)."

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug")
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--fornecedor", choices=[f.value for f in Fornecedor], default=None)
        parser.add_argument("--skus", default=None, help="Lista explícita de SKUs (por vírgula).")
        parser.add_argument(
            "--so-reconciliar",
            action="store_true",
            help="Nunca envia anexos; só reconcilia o marcador local dos produtos "
            "que o Tiny já tem (contagem suficiente). Para o caso MC511.",
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        dry_run = options["dry_run"]
        so_reconciliar = options["so_reconciliar"]
        w = self.stdout.write
        if dry_run:
            w(self.style.WARNING("DRY-RUN — nenhuma escrita no Tiny e nenhuma alteração local."))
        if so_reconciliar:
            w(self.style.WARNING("SÓ RECONCILIAR — nenhum PUT de anexo; só marca o que o Tiny já tem."))

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

        # somente_leitura no --dry-run E no --so-reconciliar (este último não
        # deve poder escrever anexo nem por engano).
        cliente = TinyApiClient(instancia, somente_leitura=dry_run or so_reconciliar)
        enviadas = ja_ok = reconciliados = sem_imagem = pendentes = erros = 0

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
                w(f"{rot}: marcador já cobre {len(desejadas)} imagem(ns) — pulado (sem GET)")
                continue

            try:
                atuais = cliente.anexos_do_produto(int(variacao.tiny_id))  # GET
            except Exception as exc:
                erros += 1
                self._registrar_erro(variacao, f"Falha ao consultar anexos: {exc}", dry_run)
                self.stderr.write(f"{rot}: erro ao consultar anexos: {exc}")
                continue

            if len(atuais) >= len(desejadas):
                # Tiny já tem imagens suficientes (URLs internas S3, opacas
                # para nós). NÃO reenvia — só reconcilia o marcador com as
                # URLs originais do fornecedor.
                reconciliados += 1
                self._marcar_sincronizadas(variacao, desejadas, dry_run)
                w(f"{rot}: Tiny já tem {len(atuais)} anexo(s) (>= {len(desejadas)} desejada(s)) — "
                  f"marcador reconciliado, nada enviado")
                continue

            if so_reconciliar:
                pendentes += 1
                w(f"{rot}: Tiny tem só {len(atuais)}/{len(desejadas)} — precisa de PUT "
                  f"(rode sem --so-reconciliar)")
                continue

            w(f"{rot}: PUT com {len(desejadas)} imagem(ns), externo=false (Tiny vai baixar/hospedar); "
              f"Tiny hoje tem {len(atuais)}")
            if dry_run:
                for u in desejadas:
                    w(f"    -> {u}")
                continue

            try:
                cliente.sincronizar_anexos_produto(int(variacao.tiny_id), desejadas)
                self._marcar_sincronizadas(variacao, desejadas, dry_run)
                enviadas += 1
            except Exception as exc:  # NÃO perde o vínculo do produto já criado
                erros += 1
                self._registrar_erro(variacao, f"Falha ao sincronizar imagens: {exc}", dry_run)
                self.stderr.write(f"{rot}: erro ao sincronizar imagens: {exc}")

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if dry_run else ''}"
            f"Enviadas (PUT): {enviadas} | reconciliadas: {reconciliados} | "
            f"marcador já cobria: {ja_ok} | sem imagem: {sem_imagem} | "
            f"pendentes (só-reconciliar): {pendentes} | erros: {erros}"
        ))

    # -- persistência local -----------------------------------------

    @staticmethod
    def _marcar_sincronizadas(variacao, urls_originais, dry_run):
        if dry_run:
            return
        variacao.imagens_tiny_sincronizadas = sorted(set(urls_originais))[:MAX_ANEXOS_POR_PRODUTO]
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
