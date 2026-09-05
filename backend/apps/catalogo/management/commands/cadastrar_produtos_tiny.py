from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import StatusVariacao, Variacao

# Regra do passo 6: nenhum limite foi dado pelo cliente para quantos
# anexos (imagens) mandar por produto — escolhido por nós. 5 cobre a
# imagem principal + a galeria típica dos fornecedores sem inflar o
# payload à toa (documentado no README).
MAX_ANEXOS_POR_PRODUTO = 5


class Command(BaseCommand):
    """
    Cadastra no Tiny as variações com status pendente desta instância.

    Idempotente e retomável por construção: cada variação processada com
    sucesso sai de `pendente` (vira `cadastrado` ou `erro`) e não é mais
    selecionada pela consulta — então rodar de novo depois de uma
    interrupção simplesmente continua nas que ainda restam, sem checkpoint
    separado nenhum.
    """

    help = "Cadastra no Tiny as variações pendentes de uma instância (uma Variacao = um produto)."

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug")
        parser.add_argument(
            "--limite", type=int, default=None, help="Máximo de variações a processar nesta execução."
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        self._validar_configuracao(instancia)

        cliente = TinyApiClient(instancia)

        fila = Variacao.objects.filter(
            produto__instancia=instancia, status=StatusVariacao.PENDENTE
        ).order_by("id")
        if options["limite"]:
            fila = fila[: options["limite"]]

        processadas = cadastradas = vinculadas = erros = sem_ncm = 0

        for variacao in fila.iterator():
            try:
                resultado = self._processar_variacao(cliente, instancia, variacao)
                if resultado == "cadastrada":
                    cadastradas += 1
                else:
                    vinculadas += 1
                if not variacao.ncm:
                    # Correção do passo 6: NCM não é obrigatório no Tiny (só
                    # sku/descricao/tipo são) — o cadastro segue normalmente.
                    # Isso só fica registrado como aviso, não como erro, para
                    # não travar o lote esperando o fornecedor responder.
                    sem_ncm += 1
                    self.stdout.write(
                        self.style.WARNING(f"[{variacao.sku}] cadastrado/vinculado SEM NCM.")
                    )
            except Exception as exc:  # uma variação ruim não pode travar o lote
                erros += 1
                self._marcar_erro(variacao, str(exc))
                self.stderr.write(f"[{variacao.sku}] erro: {exc}")
            processadas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Processadas: {processadas} | cadastradas: {cadastradas} | "
                f"vinculadas (já existiam no Tiny): {vinculadas} | erros: {erros}"
            )
        )
        if sem_ncm:
            self.stdout.write(
                self.style.WARNING(
                    f"{sem_ncm} variação(ões) cadastrada(s)/vinculada(s) SEM NCM — pendência "
                    "fiscal a cobrar do fornecedor (não bloqueou o cadastro)."
                )
            )

    # -- passos -----------------------------------------------------------

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None

    def _validar_configuracao(self, instancia):
        # Regra do cliente: origem/unidade não têm valor fixo no código —
        # precisam estar configurados por instância antes de cadastrar.
        # (NCM não entra aqui: é opcional de verdade no Tiny — ver handle().)
        faltando = []
        if instancia.tiny_origem_padrao is None:
            faltando.append("tiny_origem_padrao")
        if not instancia.tiny_unidade_medida_padrao:
            faltando.append("tiny_unidade_medida_padrao")
        if faltando:
            raise CommandError(
                f"Configure {', '.join(faltando)} na instância '{instancia.slug}' "
                "(admin) antes de cadastrar produtos."
            )
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

    def _processar_variacao(self, cliente, instancia, variacao):
        produto_existente = cliente.buscar_produto_por_sku(variacao.sku)
        if produto_existente:
            self._marcar_cadastrada(variacao, produto_existente["id"])
            return "vinculada"

        payload = montar_payload_produto(variacao, instancia)
        resultado = cliente.criar_produto(payload)
        self._marcar_cadastrada(variacao, resultado["id"])
        return "cadastrada"

    @staticmethod
    def _marcar_cadastrada(variacao, tiny_id):
        variacao.tiny_id = str(tiny_id)
        variacao.status = StatusVariacao.CADASTRADO
        variacao.cadastrado_em = timezone.now()
        variacao.ultimo_erro = ""
        variacao.save(update_fields=["tiny_id", "status", "cadastrado_em", "ultimo_erro", "atualizado_em"])

    @staticmethod
    def _marcar_erro(variacao, mensagem):
        variacao.status = StatusVariacao.ERRO
        variacao.ultimo_erro = mensagem
        variacao.save(update_fields=["status", "ultimo_erro", "atualizado_em"])


def montar_payload_produto(variacao, instancia):
    """
    Regra do cliente: cada Variacao vira um produto Simples ('S') próprio no
    Tiny, com o SKU do fornecedor como código. Contrato conferido em
    https://api-docs.erp.olist.com/api-reference/produtos/criar-produto.md
    (passo 6): só sku, descricao e tipo são obrigatórios — todo o resto,
    incluindo ncm, é nullable, então nunca omitimos o cadastro por falta de
    um campo opcional.
    """
    payload = {
        "sku": variacao.sku,
        "descricao": variacao.nome,
        "tipo": "S",
        "unidade": instancia.tiny_unidade_medida_padrao,
        "origem": instancia.tiny_origem_padrao,
        "ncm": variacao.ncm or None,
        "precos": {"preco": float(variacao.preco_venda_tiny)},
        "estoque": {"inicial": float(variacao.estoque), "controlar": True},
    }

    dimensoes = _montar_dimensoes(variacao)
    if dimensoes:
        payload["dimensoes"] = dimensoes

    anexos = _montar_anexos(variacao)
    if anexos:
        payload["anexos"] = anexos

    garantia = (variacao.atributos or {}).get("garantia_do_produto")
    if garantia:
        payload["garantia"] = garantia

    return payload


def _montar_dimensoes(variacao):
    """Só inclui o objeto `dimensoes` se pelo menos um campo foi normalizado (nunca manda tudo em branco)."""
    campos = {
        "largura": variacao.largura,
        "altura": variacao.altura,
        "comprimento": variacao.comprimento,
        "diametro": variacao.diametro,
        "pesoLiquido": variacao.peso_liquido,
        "pesoBruto": variacao.peso_bruto,
    }
    preenchidos = {k: v for k, v in campos.items() if v is not None}
    return preenchidos or None


def _montar_anexos(variacao):
    """
    MELHORIA 2 (passo 6): imagens já normalizadas no espelho (`Variacao.imagens`)
    viram anexos externos — o Tiny só guarda o link, sem subir arquivo.
    XBZ/Asia/Só Marcas já entregam URL absoluta; a Spot só entra na lista
    quando `ConfiguracaoFornecedor.url_base_imagens` estiver preenchido
    (enquanto vazio, `Variacao.imagens` já vem vazia para ela — nada a
    fazer aqui). Limitado a MAX_ANEXOS_POR_PRODUTO por produto.
    """
    urls = [u for u in (variacao.imagens or []) if u][:MAX_ANEXOS_POR_PRODUTO]
    return [{"url": url, "externo": True} for url in urls]
