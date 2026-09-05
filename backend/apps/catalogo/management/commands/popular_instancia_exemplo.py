from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.instancias.models import CredencialFornecedor, Instancia

from ...models import Produto, Variacao

NOME_INSTANCIA_EXEMPLO = "Loja Exemplo"


class Command(BaseCommand):
    help = (
        "Popula uma instância de exemplo com credenciais fictícias e alguns "
        "produtos/variações representativos dos quatro fornecedores. Uso "
        "exclusivo de desenvolvimento — os valores não são dados reais de "
        "nenhum fornecedor, apenas ilustram os formatos vistos em samples/."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--nome",
            default=NOME_INSTANCIA_EXEMPLO,
            help="Nome da instância de exemplo a criar (padrão: %(default)r).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        nome = options["nome"]
        instancia, criada = Instancia.objects.get_or_create(nome=nome)
        if criada:
            self.stdout.write(self.style.SUCCESS(f"Instância '{instancia}' criada (slug={instancia.slug})."))
        else:
            self.stdout.write(f"Instância '{instancia}' já existia (slug={instancia.slug}).")

        self._criar_credenciais_exemplo(instancia)
        self._criar_catalogo_exemplo(instancia)

        self.stdout.write(self.style.SUCCESS("Concluído."))

    def _criar_credenciais_exemplo(self, instancia):
        exemplos = {
            "xbz": {"cnpj": "00000000000000", "token": "TOKEN-EXEMPLO"},
            "asia": {"api_key": "api-key-exemplo", "secret_key": "secret-key-exemplo"},
            # Só Marcas: sem amostra real ainda (credenciais do cliente pendentes).
            # Formato assumido a partir da especificação do fornecedor, não validado.
            "somarcas": {"usuario": "", "senha": "", "estado": "SP"},
            "spot": {"client_id": "00000", "access_key": "access-key-exemplo"},
        }
        for fornecedor, credenciais in exemplos.items():
            ativo = bool(credenciais.get("usuario") or fornecedor != "somarcas")
            _, criada = CredencialFornecedor.objects.get_or_create(
                instancia=instancia,
                fornecedor=fornecedor,
                defaults={"credenciais": credenciais, "ativo": ativo},
            )
            if criada:
                self.stdout.write(f"  credencial de exemplo criada para '{fornecedor}'")

    def _criar_catalogo_exemplo(self, instancia):
        # xbz: produto normal com duas cores, uma com estoque e outra zerada
        produto_xbz = self._get_or_create_produto(
            instancia,
            fornecedor="xbz",
            codigo_pai="06520",
            nome="Caneca Acrílica 400ml Com Tampa",
            descricao="Caneca acrílica 400ml com detalhe oval no pegador.",
        )
        self._get_or_create_variacao(
            produto_xbz, sku="06520-AZU", nome="Caneca Acrílica 400ml Azul",
            cor="AZUL", ncm="73239300", preco=Decimal("6.90"), estoque=120,
        )
        self._get_or_create_variacao(
            produto_xbz, sku="06520-VD", nome="Caneca Acrílica 400ml Verde",
            cor="VERDE", ncm="73239300", preco=Decimal("6.90"), estoque=0,
        )

        # xbz: produto saindo de linha (regra do prefixo "P@") — nunca deve
        # ser cadastrado; Produto.save() marca descontinuado automaticamente.
        produto_xbz_saindo = self._get_or_create_produto(
            instancia,
            fornecedor="xbz",
            codigo_pai="P@12288",
            nome="Galão Dobrável 3 Litros",
            descricao="Galão dobrável saindo de linha.",
        )
        self._get_or_create_variacao(
            produto_xbz_saindo, sku="P@12288-AZE", nome="Galão Dobrável 3L Azul",
            cor="AZUL", ncm="39269090", preco=Decimal("2.99"), estoque=6152,
        )

        # asia: produto com variações de cor, cada uma com seu próprio ncm
        produto_asia = self._get_or_create_produto(
            instancia,
            fornecedor="asia",
            codigo_pai="MC511P",
            nome="Bolsa Multifuncional em Poliéster 300D",
            descricao="Bolsa multifuncional em poliéster 300D com detalhes em PU.",
        )
        self._get_or_create_variacao(
            produto_asia, sku="MC511-CINZA", nome="Bolsa Multifuncional Cinza",
            cor="CINZA", ncm="4202.92.00", preco=Decimal("45.00"), estoque=675,
        )

        # spot: produto-base (sem cores separadas na amostra de exemplo)
        produto_spot = self._get_or_create_produto(
            instancia,
            fornecedor="spot",
            codigo_pai="11103",
            nome="Borracha Branca em TPR",
            descricao="Borracha branca em TPR, produto certificado Inmetro.",
        )
        self._get_or_create_variacao(
            produto_spot, sku="11103-103", nome="Borracha Branca em TPR Preta",
            cor="Preto",
            # NCM não preenchido de propósito: a Spot só fornece "Taric",
            # ainda não confirmado como equivalente ao NCM brasileiro.
            preco=Decimal("1.20"), estoque=232535,
        )

    def _get_or_create_produto(self, instancia, *, fornecedor, codigo_pai, nome, descricao):
        produto, criada = Produto.objects.get_or_create(
            instancia=instancia,
            fornecedor=fornecedor,
            codigo_pai=codigo_pai,
            defaults={"nome": nome, "descricao": descricao, "payload_bruto": {"exemplo": True}},
        )
        if criada:
            self.stdout.write(f"  produto de exemplo criado: [{fornecedor}] {codigo_pai}")
        return produto

    def _get_or_create_variacao(self, produto, *, sku, nome, preco, estoque, **extra):
        variacao, criada = Variacao.objects.get_or_create(
            produto=produto,
            sku=sku,
            defaults={
                "nome": nome,
                "preco": preco,
                "estoque": estoque,
                "payload_bruto": {"exemplo": True},
                **extra,
            },
        )
        if criada:
            self.stdout.write(f"    variação de exemplo criada: {sku} (status={variacao.status})")
        return variacao
