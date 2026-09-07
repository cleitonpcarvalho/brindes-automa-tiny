from django.core.management.base import BaseCommand

from apps.catalogo.models import Variacao
from apps.instancias.constants import Fornecedor

from ...spot import _ncm_do_taric


class Command(BaseCommand):
    """
    Preenche `Variacao.ncm` das variações da Spot a partir do `Taric` já
    salvo em `Variacao.payload_bruto` (a linha de `optionalsComplete`),
    aplicando a MESMA regra do normalizador (`_ncm_do_taric`): só aproveita
    quando o Taric tem 8 dígitos; 9-10 dígitos (código CN/TARIC da UE)
    continuam sem NCM. Não usa a API da Spot — só o payload já no banco.

    Por que existe: passar a mapear o NCM no código NÃO muda o hash do
    payload, então `importar_fornecedor` ignoraria as variações Spot já
    existentes (mesmo hash => "ignorado"). Este comando as atualiza sem
    depender de reimportação.

    Escopo do que é tocado: SÓ `Variacao.ncm` (e `atualizado_em`). O
    `save()` roda com `update_fields` restrito — status, tiny_id, preço,
    estoque, imagens, marcadores de sincronização, `hash_conteudo`,
    `payload_bruto`, cor e qualquer outro campo ficam como estavam. O
    `Taric` cru em `atributos['taric']` também não é tocado.

    Opções:
      --dry-run           não grava nada, só relata o que mudaria;
      --instancia <slug>  limita a uma instância (padrão: todas);
      --limite <n>        processa no máximo n variações.
    """

    help = "Backfill de Variacao.ncm das variações Spot a partir do Taric salvo no payload_bruto."

    def add_arguments(self, parser):
        parser.add_argument("--instancia", default=None, help="slug da instância (padrão: todas).")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limite", type=int, default=None)

    def handle(self, *args, **options):
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

        atualizadas = inalteradas = sem_ncm = 0
        for variacao in fila:
            opcional = variacao.payload_bruto or {}
            produto_bruto = variacao.produto.payload_bruto or {}
            taric = opcional.get("Taric") or produto_bruto.get("Taric") or ""
            novo = _ncm_do_taric(taric)

            if novo == (variacao.ncm or ""):
                inalteradas += 1
                if not novo:
                    sem_ncm += 1
                continue

            atualizadas += 1
            w(f"[instancia {variacao.produto.instancia_id}] {variacao.sku}: "
              f"ncm {variacao.ncm!r} -> {novo!r}  (Taric cru: {taric!r})")
            if not dry_run:
                variacao.ncm = novo
                variacao.save(update_fields=["ncm", "atualizado_em"])

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if dry_run else ''}"
            f"Atualizadas: {atualizadas} | inalteradas: {inalteradas} | "
            f"seguem sem NCM (Taric não tem 8 dígitos): {sem_ncm}"
        ))
