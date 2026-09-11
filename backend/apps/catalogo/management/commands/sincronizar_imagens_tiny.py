from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient
from apps.sincronizacao.locks import lock_instancia_tiny

from ...tiny_sync import (
    IMG_ENVIADA,
    IMG_JA_OK,
    IMG_PENDENTE,
    IMG_RECONCILIADA,
    IMG_SEM_IMAGEM,
    fila_imagens,
    registrar_erro_imagem,
    sincronizar_imagens_variacao,
)


class Command(BaseCommand):
    """
    Replica no Tiny as imagens do fornecedor para produtos JÁ cadastrados
    (`status=cadastrado` com `tiny_id`), via `PUT /produtos/{id}/anexos`
    com `externo=false` (o Tiny BAIXA a imagem e a hospeda — confirmado no
    MC511; com `externo=true` a URL ficava registrada mas a imagem não
    aparecia no ERP).

    A lógica de idempotência vive em `apps.catalogo.tiny_sync`
    (`sincronizar_imagens_variacao`) — a MESMA usada pela sincronização em
    massa (task/UI). Este comando é só a interface de linha de comando.

    IDEMPOTÊNCIA (marcador local `Variacao.imagens_tiny_sincronizadas` = URLs
    ORIGINAIS já sincronizadas):
      1. marcador já cobre tudo -> nada a fazer (sem GET);
      2. senão, GET dos anexos: se o Tiny já tem QUANTIDADE >= a desejada
         (produto já internalizado — ex.: MC511 à mão), NÃO reenvia, só
         reconcilia o marcador;
      3. senão, PUT com a lista completa e marca todas.
    Falha ao sincronizar NÃO altera status nem `tiny_id` — só grava
    `ultimo_erro` e tenta de novo na próxima rodada. Reexecução após
    sucesso não faz nenhuma escrita nem chamada.

    `--dry-run`: nenhuma escrita (Tiny ou local) — só o GET de diagnóstico.
    `--so-reconciliar`: NUNCA chama o endpoint de anexos; só reconcilia o
    marcador dos produtos que o Tiny já tem (contagem >= desejada). Caso MC511.
    Seleção: `--fornecedor`, `--skus` (por vírgula), `--limite`.
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
        if options["dry_run"] or options["so_reconciliar"]:
            return self._handle(*args, instancia=instancia, **options)
        with lock_instancia_tiny(instancia.id) as adquirida:
            if not adquirida:
                raise CommandError("A conta Tiny desta instância está ocupada por outra propagação.")
            return self._handle(*args, instancia=instancia, **options)

    def _handle(self, *args, instancia, **options):
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        dry_run = options["dry_run"]
        so_reconciliar = options["so_reconciliar"]
        w = self.stdout.write
        if dry_run:
            w(self.style.WARNING("DRY-RUN — nenhuma escrita no Tiny e nenhuma alteração local."))
        if so_reconciliar:
            w(self.style.WARNING("SÓ RECONCILIAR — nenhum PUT de anexo; só marca o que o Tiny já tem."))

        skus = [s.strip() for s in (options["skus"] or "").split(",") if s.strip()]
        fila = fila_imagens(
            instancia,
            fornecedor=options["fornecedor"],
            skus=skus or None,
            limite=options["limite"],
        )

        # somente_leitura no dry-run E no só-reconciliar (este último não
        # pode escrever anexo nem por engano).
        cliente = TinyApiClient(instancia, somente_leitura=dry_run or so_reconciliar)
        enviadas = ja_ok = reconciliados = sem_imagem = pendentes = erros = 0

        for variacao in fila:
            rot = f"[{variacao.produto.fornecedor}] {variacao.sku!r} (tiny_id={variacao.tiny_id})"
            try:
                r = sincronizar_imagens_variacao(
                    cliente, variacao, so_reconciliar=so_reconciliar, dry_run=dry_run
                )
            except Exception as exc:  # NÃO perde o vínculo do produto já criado
                erros += 1
                if not dry_run:
                    registrar_erro_imagem(variacao, f"Falha ao sincronizar imagens: {exc}")
                self.stderr.write(f"{rot}: erro ao sincronizar imagens: {exc}")
                continue

            desejadas = r["desejadas"]
            atuais = r["atuais"]
            resultado = r["resultado"]
            if resultado == IMG_SEM_IMAGEM:
                sem_imagem += 1
                w(f"{rot}: sem imagem utilizável no espelho — mantém sem imagem")
            elif resultado == IMG_JA_OK:
                ja_ok += 1
                w(f"{rot}: marcador já cobre {len(desejadas)} imagem(ns) — pulado (sem GET)")
            elif resultado == IMG_RECONCILIADA:
                reconciliados += 1
                w(f"{rot}: Tiny já tem {atuais} anexo(s) (>= {len(desejadas)} desejada(s)) — "
                  f"marcador reconciliado, nada enviado")
            elif resultado == IMG_PENDENTE:
                pendentes += 1
                w(f"{rot}: Tiny tem só {atuais}/{len(desejadas)} — precisa de PUT "
                  f"(rode sem --so-reconciliar)")
            elif resultado == IMG_ENVIADA:
                enviadas += 1
                w(f"{rot}: PUT com {len(desejadas)} imagem(ns), externo=false "
                  f"(Tiny vai baixar/hospedar); Tiny hoje tem {atuais}")
                if dry_run:
                    for u in desejadas:
                        w(f"    -> {u}")

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if dry_run else ''}"
            f"Enviadas (PUT): {enviadas} | reconciliadas: {reconciliados} | "
            f"marcador já cobria: {ja_ok} | sem imagem: {sem_imagem} | "
            f"pendentes (só-reconciliar): {pendentes} | erros: {erros}"
        ))

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
