from decimal import Decimal
from unittest.mock import patch
from unittest.mock import MagicMock

from django.test import TestCase

from apps.instancias.models import CredencialFornecedor, Instancia

from ..models import Produto, StatusVariacao, Variacao


def _com_tiny_fornecedor_id(instancia, fornecedor, tiny_id=700_000_000):
    """Garante o id do contato-fornecedor no Tiny para o par — sem ele o
    cadastro de novos produtos fica bloqueado."""
    CredencialFornecedor.objects.update_or_create(
        instancia=instancia, fornecedor=fornecedor, defaults={"tiny_fornecedor_id": tiny_id}
    )
from ..tiny_sync import (
    PARADA_LEASE_PERDIDA,
    PARADA_PAUSA,
    ControladorSincronizacao,
    estimar_cadastro,
    executar_sincronizacao_tiny,
    atualizar_variacao_individual,
)


def _instancia(**kwargs):
    dados = {
        "nome": "Loja Tiny Sync",
        "access_token": "token-valido",
        "tiny_origem_padrao": 0,
        "tiny_unidade_medida_padrao": "UN",
    }
    dados.update(kwargs)
    return Instancia.objects.create(**dados)


def _variacao(instancia, sku, *, fornecedor="xbz", codigo_pai=None, estoque=5, status=None, **kwargs):
    produto = Produto.objects.create(
        instancia=instancia,
        fornecedor=fornecedor,
        codigo_pai=codigo_pai or f"pai-{sku}",
        nome=f"Produto {sku}",
    )
    dados = {
        "produto": produto,
        "sku": sku,
        "nome": f"Variação {sku}",
        "preco": Decimal("10.00"),
        "estoque": estoque,
        "payload_bruto": {"CodigoComposto": sku} if fornecedor == "xbz" else {},
        "atributos": {"codigo_composto": sku} if fornecedor == "xbz" else {},
    }
    dados.update(kwargs)
    v = Variacao.objects.create(**dados)
    if status is not None and v.status != status:
        Variacao.objects.filter(pk=v.pk).update(status=status)
        v.refresh_from_db()
    _com_tiny_fornecedor_id(instancia, fornecedor)
    return v


class _MockTiny:
    """Substitui os métodos de rede do TinyApiClient. Nada sai para o Tiny."""

    def __init__(self, *, skus_existentes=None, criar_efeito=None, anexos=None, anexos_efeito=None):
        self.skus_existentes = skus_existentes or {}
        self.criar_efeito = criar_efeito
        self.anexos = anexos if anexos is not None else []
        self.anexos_efeito = anexos_efeito
        self.criados = []
        self.anexos_enviados = []

    def buscar_produto_por_sku(self, sku):
        return self.skus_existentes.get(sku)

    def criar_produto(self, payload):
        self.criados.append(payload)
        if self.criar_efeito:
            return self.criar_efeito(payload)
        return {"id": 90000 + len(self.criados), "sku": payload["sku"]}

    def anexos_do_produto(self, id_produto):
        return list(self.anexos)

    def sincronizar_anexos_produto(self, id_produto, urls):
        if self.anexos_efeito:
            self.anexos_efeito(id_produto, list(urls))
        self.anexos_enviados.append((id_produto, list(urls)))
        return {}


def _rodar(instancia, fornecedor, mock, **kwargs):
    return executar_sincronizacao_tiny(instancia, fornecedor, cliente=mock, **kwargs)


class OrquestradorTests(TestCase):
    @patch("apps.catalogo.tiny_sync._sincronizar_imagens_do_sku")
    def test_atualizacao_existente_xbz_publica_codigo_composto(self, _imagens):
        inst = _instancia()
        v = _variacao(
            inst,
            "X134066",
            payload_bruto={"CodigoComposto": "18700-AZU"},
            atributos={"codigo_composto": "18700-AZU"},
            status=StatusVariacao.CADASTRADO,
            tiny_id="123",
        )
        cliente = MagicMock()
        cliente.obter_produto.return_value = {"id": 123, "sku": "X134066", "fornecedores": []}

        atualizar_variacao_individual(inst, v, cliente=cliente)

        payload = cliente.atualizar_produto.call_args.args[1]
        self.assertEqual(payload["sku"], "18700-AZU")
        self.assertEqual(payload["fornecedores"][0]["codigoProdutoNoFornecedor"], "18700-AZU")
        self.assertEqual(payload["precos"]["preco"], 0.0)
        cliente.atualizar_estoque.assert_called_once()
        cliente.criar_produto.assert_not_called()
        v.refresh_from_db()
        self.assertEqual(v.tiny_id, "123")

    def test_variacao_elegivel_e_criada_no_tiny(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-OK")
        mock = _MockTiny()

        r = _rodar(inst, "xbz", mock)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(v.tiny_id, "90001")
        self.assertEqual(r.criadas, 1)
        self.assertEqual([p["sku"] for p in mock.criados], ["SKU-OK"])

    def test_estoque_zero_nao_e_cadastrado(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-ZERO", estoque=0)  # save() -> status aguardando
        self.assertEqual(v.status, StatusVariacao.AGUARDANDO)
        mock = _MockTiny()

        r = _rodar(inst, "xbz", mock)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.AGUARDANDO)  # intacto
        self.assertEqual(mock.criados, [])
        self.assertEqual(r.fila, 0)

    def test_xbz_p_arroba_nao_e_cadastrado(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-PA", codigo_pai="P@12345")  # Produto.save() -> descontinuado
        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.DESCONTINUADO)
        mock = _MockTiny()

        r = _rodar(inst, "xbz", mock)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.DESCONTINUADO)
        self.assertEqual(mock.criados, [])
        self.assertEqual(r.fila, 0)

    def test_sku_ja_existente_sem_vinculo_e_bloqueado(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-ANTIGO")
        mock = _MockTiny(skus_existentes={"SKU-ANTIGO": {"id": 555, "sku": "SKU-ANTIGO"}})

        r = _rodar(inst, "xbz", mock)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.PENDENTE)  # intacto
        self.assertIsNone(v.tiny_id)
        self.assertEqual(mock.criados, [])
        self.assertEqual(r.bloqueadas, 1)

    def test_produto_ja_sincronizado_nao_e_recriado(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-FEITO", status=StatusVariacao.CADASTRADO, tiny_id="123")
        mock = _MockTiny()

        r = _rodar(inst, "xbz", mock)

        self.assertEqual(mock.criados, [])
        self.assertEqual(r.fila, 0)  # cadastrado não entra na fila

    def test_erro_individual_nao_aborta_o_lote(self):
        inst = _instancia()
        bom1 = _variacao(inst, "BOM-1")
        ruim = _variacao(inst, "RUIM")
        bom2 = _variacao(inst, "BOM-2")

        def efeito(payload):
            if payload["sku"] == "RUIM":
                raise RuntimeError("Tiny recusou")
            return {"id": 700, "sku": payload["sku"]}

        mock = _MockTiny(criar_efeito=efeito)
        r = _rodar(inst, "xbz", mock)

        bom1.refresh_from_db()
        bom2.refresh_from_db()
        ruim.refresh_from_db()
        self.assertEqual(bom1.status, StatusVariacao.CADASTRADO)
        self.assertEqual(bom2.status, StatusVariacao.CADASTRADO)
        self.assertEqual(ruim.status, StatusVariacao.ERRO)
        self.assertIn("Tiny recusou", ruim.ultimo_erro)
        self.assertEqual(r.criadas, 2)
        self.assertEqual(r.erros, 1)

    def test_imagens_sincronizadas_apos_a_criacao(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-IMG", fornecedor="asia", imagens=["https://cdn/x.jpg"])
        mock = _MockTiny(anexos=[])  # Tiny ainda não tem anexo

        r = _rodar(inst, "asia", mock)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(len(mock.anexos_enviados), 1)
        self.assertEqual(mock.anexos_enviados[0][1], ["https://cdn/x.jpg"])
        self.assertEqual(v.imagens_tiny_sincronizadas, ["https://cdn/x.jpg"])
        self.assertEqual(r.imagens_enviadas, 1)

    def test_reexecucao_e_idempotente(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-IDEM", fornecedor="asia", imagens=["https://cdn/y.jpg"])
        mock = _MockTiny(anexos=[])

        _rodar(inst, "asia", mock)
        mock.anexos = ["https://s3/interno.jpg"]  # Tiny agora tem 1
        r2 = _rodar(inst, "asia", mock)

        v.refresh_from_db()
        self.assertEqual(len(mock.criados), 1)  # criado só na 1ª rodada
        self.assertEqual(len(mock.anexos_enviados), 1)  # imagem enviada só na 1ª
        self.assertEqual(r2.fila, 0)  # nada mais pendente
        self.assertEqual(r2.criadas, 0)

    def test_erro_de_imagem_nao_recria_produto_e_fica_registrado(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-IMGERR", fornecedor="asia", imagens=["https://cdn/e.jpg"])

        def falha(_id, _urls):
            raise RuntimeError("Tiny recusou o anexo")

        mock = _MockTiny(anexos=[], anexos_efeito=falha)
        r = _rodar(inst, "asia", mock)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)  # produto criado mesmo assim
        self.assertEqual(v.tiny_id, "90001")
        self.assertEqual(v.imagens_tiny_sincronizadas, [])     # NÃO marcou como sincronizada
        self.assertIn("anexo", v.ultimo_erro)
        self.assertEqual(r.criadas, 1)
        self.assertEqual(r.imagens_erros, 1)

        # retomada: NÃO recria o produto; só retenta a imagem
        mock.anexos_efeito = None
        r2 = _rodar(inst, "asia", mock)

        v.refresh_from_db()
        self.assertEqual(len(mock.criados), 1)                 # sem recriação
        self.assertEqual(r2.criadas, 0)
        self.assertEqual(r2.imagens_enviadas, 1)
        self.assertEqual(v.imagens_tiny_sincronizadas, ["https://cdn/e.jpg"])

        r3 = _rodar(inst, "asia", mock)
        self.assertEqual(r3.fila, 0)                           # nada mais pendente

    def test_pausa_ocorre_depois_da_etapa_de_imagens_do_sku(self):
        inst = _instancia()
        a = _variacao(inst, "PA-A", fornecedor="asia", imagens=["https://cdn/a.jpg"])
        b = _variacao(inst, "PA-B", fornecedor="asia", imagens=["https://cdn/b.jpg"])
        mock = _MockTiny(anexos=[])
        # segue no A; pede pausa antes do B
        ctrl = _ControladorSequencia([None, PARADA_PAUSA])

        r = _rodar(inst, "asia", mock, controlador=ctrl)

        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(r.interrompida_por, PARADA_PAUSA)
        self.assertEqual(a.status, StatusVariacao.CADASTRADO)
        # a imagem do A foi enviada ANTES de a pausa ser atendida
        self.assertEqual(a.imagens_tiny_sincronizadas, ["https://cdn/a.jpg"])
        self.assertEqual([urls for _id, urls in mock.anexos_enviados], [["https://cdn/a.jpg"]])
        self.assertEqual(r.imagens_enviadas, 1)
        self.assertEqual(b.status, StatusVariacao.PENDENTE)  # B nem começou

    def test_isolamento_por_fornecedor(self):
        inst = _instancia()
        xbz = _variacao(inst, "X-1", fornecedor="xbz")
        asia = _variacao(inst, "A-1", fornecedor="asia")
        mock = _MockTiny()

        _rodar(inst, "xbz", mock)

        xbz.refresh_from_db()
        asia.refresh_from_db()
        self.assertEqual(xbz.status, StatusVariacao.CADASTRADO)
        self.assertEqual(asia.status, StatusVariacao.PENDENTE)  # intacto
        self.assertEqual([p["sku"] for p in mock.criados], ["X-1"])

    def test_isolamento_entre_instancias(self):
        inst_a = _instancia(nome="A")
        inst_b = _instancia(nome="B")
        va = _variacao(inst_a, "SKU-DUP", fornecedor="xbz")
        vb = _variacao(inst_b, "SKU-DUP", fornecedor="xbz")
        mock = _MockTiny()

        _rodar(inst_a, "xbz", mock)

        va.refresh_from_db()
        vb.refresh_from_db()
        self.assertEqual(va.status, StatusVariacao.CADASTRADO)
        self.assertEqual(vb.status, StatusVariacao.PENDENTE)

    def test_colisao_cross_fornecedor_e_bloqueada(self):
        inst = _instancia()
        _variacao(inst, "COLIDE", fornecedor="xbz")
        _variacao(inst, "COLIDE", fornecedor="asia")
        mock = _MockTiny()

        r = _rodar(inst, "xbz", mock)

        self.assertEqual(mock.criados, [])
        self.assertEqual(r.bloqueadas, 1)

    def test_retry_de_erro_e_reprocessado(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-RETRY", status=StatusVariacao.ERRO, ultimo_erro="falha antiga")
        mock = _MockTiny()

        r = _rodar(inst, "xbz", mock)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(r.criadas, 1)

    def test_nao_toca_no_tiny_em_dry_run(self):
        inst = _instancia()
        _variacao(inst, "SKU-DRY")

        with patch("apps.instancias.tiny_client.TinyApiClient.criar_produto") as mock_criar, patch(
            "apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None
        ):
            r = executar_sincronizacao_tiny(inst, "xbz", dry_run=True)

        mock_criar.assert_not_called()
        self.assertEqual(r.criadas, 1)  # "seria criada"


class _ControladorSequencia(ControladorSincronizacao):
    """Devolve, em ordem, os motivos da lista (None = seguir)."""

    def __init__(self, motivos):
        self.motivos = list(motivos)
        self.chamadas = 0

    def checar(self):
        self.chamadas += 1
        return self.motivos.pop(0) if self.motivos else None


class VinculoFornecedorNoTinyTests(TestCase):
    def test_payload_de_criacao_leva_o_bloco_fornecedores(self):
        inst = _instancia()
        _variacao(inst, "SKU-V", fornecedor="asia")
        CredencialFornecedor.objects.filter(instancia=inst, fornecedor="asia").update(
            tiny_fornecedor_id=752133514
        )
        mock = _MockTiny()

        _rodar(inst, "asia", mock)

        self.assertEqual(
            mock.criados[0]["fornecedores"],
            [{"id": 752133514, "padrao": True, "codigoProdutoNoFornecedor": "SKU-V"}],
        )

    def test_sem_tiny_fornecedor_id_bloqueia_criacao(self):
        inst = _instancia()
        v = _variacao(inst, "SKU-SEM", fornecedor="asia")
        CredencialFornecedor.objects.filter(instancia=inst, fornecedor="asia").delete()
        mock = _MockTiny()

        r = _rodar(inst, "asia", mock)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.PENDENTE)  # bloqueado, não erro
        self.assertIsNone(v.tiny_id)
        self.assertEqual(mock.criados, [])
        self.assertEqual(r.bloqueadas, 1)
        self.assertEqual(r.erros, 0)

    def test_id_resolvido_uma_unica_vez_por_rodada(self):
        inst = _instancia()
        for i in range(5):
            _variacao(inst, f"SKU-{i}", fornecedor="asia")
        mock = _MockTiny()

        with patch(
            "apps.catalogo.tiny_sync.tiny_fornecedor_id_de", return_value=752133514
        ) as mock_resolver:
            _rodar(inst, "asia", mock)

        self.assertEqual(mock_resolver.call_count, 1)
        self.assertEqual(len(mock.criados), 5)

    def test_variacao_ja_cadastrada_nao_e_bloqueada_por_falta_de_id(self):
        inst = _instancia()
        v = _variacao(
            inst, "SKU-FEITO", fornecedor="asia", status=StatusVariacao.CADASTRADO, tiny_id="42",
            imagens=["http://img/a.jpg"],
        )
        CredencialFornecedor.objects.filter(instancia=inst, fornecedor="asia").delete()
        # volta à fila só para concluir a etapa de imagens
        Variacao.objects.filter(pk=v.pk).update(imagens_tiny_sincronizadas=[])
        mock = _MockTiny(anexos=[])

        r = _rodar(inst, "asia", mock)

        self.assertEqual(r.bloqueadas, 0)
        self.assertEqual(r.ja_cadastradas, 1)
        self.assertEqual(mock.criados, [])
        self.assertEqual(mock.anexos_enviados, [(42, ["http://img/a.jpg"])])


class MontarPayloadProdutoTests(TestCase):
    def test_com_id_inclui_bloco_com_sku_exato(self):
        from ..tiny_sync import montar_payload_produto

        inst = _instancia()
        v = _variacao(inst, "SKU-EXATO", fornecedor="asia")
        payload = montar_payload_produto(v, inst, tiny_fornecedor_id=752133514)
        self.assertEqual(
            payload["fornecedores"],
            [{"id": 752133514, "padrao": True, "codigoProdutoNoFornecedor": "SKU-EXATO"}],
        )

    def test_sem_id_nao_inclui_o_bloco(self):
        from ..tiny_sync import montar_payload_produto

        inst = _instancia()
        v = _variacao(inst, "SKU-X", fornecedor="asia")
        self.assertNotIn("fornecedores", montar_payload_produto(v, inst))


class PauseResumeOrquestradorTests(TestCase):
    def test_pausa_para_antes_do_proximo_produto_sem_deixar_pela_metade(self):
        inst = _instancia()
        a = _variacao(inst, "A")
        b = _variacao(inst, "B")
        c = _variacao(inst, "C")
        mock = _MockTiny()
        # segue no 1º produto; pede pausa antes do 2º
        ctrl = _ControladorSequencia([None, PARADA_PAUSA])

        r = _rodar(inst, "xbz", mock, controlador=ctrl)

        self.assertEqual(r.interrompida_por, PARADA_PAUSA)
        self.assertEqual(r.criadas, 1)
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
        self.assertEqual(a.status, StatusVariacao.CADASTRADO)
        self.assertEqual(b.status, StatusVariacao.PENDENTE)  # não começou
        self.assertEqual(c.status, StatusVariacao.PENDENTE)
        self.assertEqual([p["sku"] for p in mock.criados], ["A"])

    def test_pausa_no_primeiro_check_nao_processa_nenhum(self):
        inst = _instancia()
        _variacao(inst, "A")
        mock = _MockTiny()
        r = _rodar(inst, "xbz", mock, controlador=_ControladorSequencia([PARADA_PAUSA]))
        self.assertEqual(r.interrompida_por, PARADA_PAUSA)
        self.assertEqual(mock.criados, [])

    def test_lease_perdida_para_o_lote_imediatamente(self):
        inst = _instancia()
        _variacao(inst, "A")
        _variacao(inst, "B")
        mock = _MockTiny()
        r = _rodar(inst, "xbz", mock, controlador=_ControladorSequencia([None, PARADA_LEASE_PERDIDA]))
        self.assertEqual(r.interrompida_por, PARADA_LEASE_PERDIDA)
        self.assertEqual(r.criadas, 1)

    def test_retomada_continua_sem_recriar_nem_reenviar_imagem(self):
        inst = _instancia()
        a = _variacao(inst, "A", fornecedor="asia", imagens=["https://cdn/a.jpg"])
        b = _variacao(inst, "B", fornecedor="asia", imagens=["https://cdn/b.jpg"])
        mock = _MockTiny(anexos=[])

        # rodada 1: processa A por inteiro (cadastro + imagens) e pausa antes de B
        r1 = _rodar(inst, "asia", mock, controlador=_ControladorSequencia([None, PARADA_PAUSA]))
        self.assertEqual(r1.criadas, 1)
        a.refresh_from_db()
        self.assertEqual(a.status, StatusVariacao.CADASTRADO)
        self.assertEqual(a.imagens_tiny_sincronizadas, ["https://cdn/a.jpg"])

        # rodada 2 (retomada): sem controlador -> processa tudo
        r2 = _rodar(inst, "asia", mock)

        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual([p["sku"] for p in mock.criados], ["A", "B"])  # A não recriado
        self.assertEqual(b.status, StatusVariacao.CADASTRADO)
        # imagem de cada um enviada exatamente 1x no total
        enviados = [sku for _id, urls in mock.anexos_enviados for sku in urls]
        self.assertEqual(sorted(enviados), ["https://cdn/a.jpg", "https://cdn/b.jpg"])
        # 3ª rodada não faz nada
        r3 = _rodar(inst, "asia", mock)
        self.assertEqual(r3.fila, 0)
        self.assertEqual(len(mock.anexos_enviados), 2)


class EstimativaTests(TestCase):
    def test_conta_elegiveis_bloqueadas_e_ja_cadastradas_sem_tocar_no_tiny(self):
        inst = _instancia()
        _variacao(inst, "OK-1", fornecedor="xbz")
        _variacao(inst, "OK-2", fornecedor="xbz")
        _variacao(inst, "ZERO", fornecedor="xbz", estoque=0)
        _variacao(inst, "PA", fornecedor="xbz", codigo_pai="P@9")
        _variacao(inst, "FEITO", fornecedor="xbz", status=StatusVariacao.CADASTRADO, tiny_id="1")
        _variacao(inst, "OUTRO", fornecedor="asia")  # não conta

        est = estimar_cadastro(inst, "xbz")

        self.assertEqual(est["elegiveis"], 2)
        self.assertEqual(est["ja_cadastradas"], 1)
        self.assertEqual(est["sem_estoque"], 1)
        self.assertEqual(est["descontinuadas"], 1)
        self.assertEqual(est["total_espelho"], 5)
