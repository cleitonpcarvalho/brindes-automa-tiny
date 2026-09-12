from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.sincronizacao.models import (
    EventoLog,
    Execucao,
    LogItem,
    NivelLog,
    StatusExecucao,
    TipoExecucao,
)

from ..models import Instancia


def _client():
    u = get_user_model().objects.create_user(email="aud@example.com", password="x")
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=u).key}")
    return c


def _variacao(instancia, sku, *, fornecedor="asia", nome=None, **kw):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=f"pai-{sku}", nome=nome or f"Produto {sku}"
    )
    dados = {"produto": produto, "sku": sku, "nome": nome or f"V {sku}", "preco": "10.00", "estoque": 5}
    dados.update(kw)
    return Variacao.objects.create(**dados)


def _log(execucao, evento, mensagem, *, variacao=None, nivel=NivelLog.INFO, **detalhe):
    return LogItem.objects.create(
        execucao=execucao, evento=evento, mensagem=mensagem, variacao=variacao, nivel=nivel, detalhe=detalhe
    )


class AuditoriaBase(TestCase):
    def setUp(self):
        self.client = _client()
        self.instancia = Instancia.objects.create(nome="Loja Asia")
        self.outra = Instancia.objects.create(nome="Loja B")
        self.execucao = Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="asia",
            tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.PAUSADO,
            iniciada_em=timezone.now() - timedelta(minutes=30),
            total_lidos=1137,
            total_cadastrados=421,
            total_erros=6,
            total_ignorados=710,
        )
        _log(self.execucao, EventoLog.GERAL, "Sincronização com o Tiny iniciada", fornecedor="asia", fila=1137)

        # 3 cadastrados, 1 vinculado, 1 bloqueado, 2 erros
        self.criadas = []
        for i in range(3):
            v = _variacao(self.instancia, f"OK-{i}", nome=f"Caneca {i}")
            v.status = StatusVariacao.CADASTRADO
            v.tiny_id = f"900{i}"
            v.save(update_fields=["status", "tiny_id"])
            _log(self.execucao, EventoLog.CRIADO, f"SKU {v.sku} criado no Tiny", variacao=v, tiny_id=f"900{i}")
            self.criadas.append(v)

        v = _variacao(self.instancia, "VINC-1", nome="Squeeze")
        _log(self.execucao, EventoLog.VINCULADO, f"SKU {v.sku} vinculado a produto existente no Tiny",
             variacao=v, tiny_id="555")

        vb = _variacao(self.instancia, "BLOQ-1", nome="Mochila")
        _log(self.execucao, EventoLog.BLOQUEADO, f"SKU {vb.sku} bloqueado", variacao=vb, nivel=NivelLog.AVISO,
             motivo="SKU já existe no Tiny (id=42) e não possui vínculo confirmado")

        self.com_erro = []
        for i in range(2):
            ve = _variacao(self.instancia, f"ERR-{i}", nome=f"Item ruim {i}")
            ve.status = StatusVariacao.ERRO
            ve.save(update_fields=["status"])
            _log(self.execucao, EventoLog.ERRO, f"Falha ao sincronizar SKU {ve.sku}", variacao=ve,
                 nivel=NivelLog.ERRO, erro=f"Tiny retornou 400: descricao obrigatória ({i})")
            self.com_erro.append(ve)

        _log(self.execucao, EventoLog.GERAL, "Sincronização pausada — pode ser retomada",
             status="pausado", cadastrados=421, erros=6)

    def _url(self, sufixo="", instancia=None, execucao=None):
        slug = (instancia or self.instancia).slug
        eid = (execucao or self.execucao).id
        return f"/api/instancias/{slug}/execucoes/{eid}/{sufixo}"


class ExecucaoDetalheResumoTests(AuditoriaBase):
    def test_retomada_de_fila_de_imagens_usa_contadores_da_tentativa(self):
        # A retomada permanece na mesma Execucao e a fila contém seis SKUs já
        # cadastrados, retornados somente para concluir imagens.
        LogItem.objects.filter(execucao=self.execucao).delete()
        _log(self.execucao, EventoLog.GERAL, "Sincronização com o Tiny iniciada", fornecedor="asia", fila=1137)
        _log(self.execucao, EventoLog.GERAL, "Execução reconhecida como interrompida", timeout_segundos=600)
        _log(self.execucao, EventoLog.GERAL, "Sincronização com o Tiny iniciada", fornecedor="asia", fila=6)
        for i in range(6):
            v = _variacao(self.instancia, f"IMG-{i}")
            v.status = StatusVariacao.CADASTRADO
            v.tiny_id = str(1000 + i)
            v.save(update_fields=["status", "tiny_id"])
            _log(
                self.execucao,
                EventoLog.GERAL,
                f"SKU {v.sku} já cadastrado no Tiny; retomando imagens",
                variacao=v,
                origem="cadastro_tiny",
                operacao="imagem_pendente",
            )
            _log(
                self.execucao,
                EventoLog.IMAGENS_ERRO,
                f"Falha ao sincronizar imagens do SKU {v.sku}",
                variacao=v,
                nivel=NivelLog.ERRO,
                erro="anexo recusado",
            )

        d = self.client.get(self._url()).data
        metricas = {m["chave"]: m["valor"] for m in d["resumo"]["metricas"]}
        self.assertEqual(self.execucao.id, d["id"])
        self.assertEqual(metricas["total_fila"], 6)
        self.assertEqual(metricas["processados"], 6)
        self.assertEqual(metricas["cadastrados"], 0)
        self.assertEqual(metricas["falhas_secundarias"], 6)
        self.assertNotIn("nenhum SKU", d["resumo"]["mensagem_logs"])
        self.assertIn("operações de imagem", d["resumo"]["mensagem_logs"])

    def test_resumo_traz_status_progresso_e_contagem_por_resultado(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        d = resp.data
        self.assertEqual(d["fornecedor"], "asia")
        self.assertEqual(d["estado"], "pausado")
        self.assertEqual(d["total_lidos"], 7)
        self.assertEqual(d["total_cadastrados"], 4)
        self.assertEqual(d["total_erros"], 2)
        self.assertEqual(d["total_ignorados"], 1)
        self.assertEqual(d["contadores_registrados"], {
            "total_lidos": 1137, "total_cadastrados": 421,
            "total_erros": 6, "total_ignorados": 710,
        })
        # A execução de cadastro usa o universo real dos logs conciliados:
        # os 7 SKUs tiveram desfecho, portanto está 100% concluída.
        self.assertEqual(d["progresso"], 1.0)
        self.assertEqual(d["resumo"]["progresso_rotulo"], "100%")
        self.assertEqual(d["auditoria"]["cadastrados"], 3)
        self.assertEqual(d["auditoria"]["vinculados"], 1)
        self.assertEqual(d["auditoria"]["bloqueados"], 1)
        self.assertEqual(d["auditoria"]["erros"], 2)
        self.assertEqual(d["auditoria"]["total"], 7)
        self.assertEqual(d["logs_gerais_total"], 2)

    def test_importacao_incremental_usa_metricas_do_espelho_e_nao_do_tiny(self):
        LogItem.objects.filter(execucao=self.execucao).delete()
        self.execucao.tipo = TipoExecucao.INCREMENTAL
        self.execucao.status = StatusExecucao.SUCESSO
        self.execucao.total_lidos = 1323
        self.execucao.total_novos = 4
        self.execucao.total_atualizados = 1318
        self.execucao.total_ignorados = 1
        self.execucao.total_erros = 0
        self.execucao.finalizada_em = timezone.now()
        self.execucao.save()

        d = self.client.get(self._url()).data
        self.assertEqual(d["progresso"], 1.0)
        self.assertEqual(
            [(m["rotulo"], m["valor"]) for m in d["resumo"]["metricas"]],
            [
                ("Itens lidos", 1323),
                ("Novos", 4),
                ("Atualizados", 1318),
                ("Ignorados / sem alteração", 1),
                ("Erros", 0),
            ],
        )
        self.assertNotIn("Cadastrados", [m["rotulo"] for m in d["resumo"]["metricas"]])
        self.assertEqual(d["resumo"]["mensagem_logs"], "Esta execução não possui processamento individual por SKU.")

    def test_falha_de_imagem_permanece_visivel_mesmo_com_todos_skus_cadastrados(self):
        v = self.criadas[0]
        self.execucao.status = StatusExecucao.PARCIAL
        self.execucao.finalizada_em = timezone.now()
        self.execucao.total_lidos = 4
        self.execucao.total_cadastrados = 4
        self.execucao.total_erros = 0
        self.execucao.total_ignorados = 0
        self.execucao.save()
        _log(
            self.execucao,
            EventoLog.IMAGENS_ERRO,
            f"Falha ao sincronizar imagens do SKU {v.sku}",
            variacao=v,
            nivel=NivelLog.ERRO,
            erro="anexo recusado pelo Tiny",
        )

        d = self.client.get(self._url()).data
        metricas = {m["chave"]: m["valor"] for m in d["resumo"]["metricas"]}
        self.assertEqual(metricas["cadastrados"], 4)
        self.assertEqual(metricas["falhas_secundarias"], 1)
        self.assertIn("falha(s) secundária(s)", d["resumo"]["motivo_status"])

    def test_colisao_com_sku_legado_nao_e_apresentada_como_erro_tecnico(self):
        LogItem.objects.filter(execucao=self.execucao).delete()
        self.execucao.status = StatusExecucao.PARCIAL
        self.execucao.finalizada_em = timezone.now()
        self.execucao.total_lidos = 1
        self.execucao.total_cadastrados = 0
        self.execucao.total_erros = 0
        self.execucao.total_ignorados = 1
        self.execucao.save()

        variacao = _variacao(self.instancia, "ME550", nome="Mala Esportiva")
        _log(
            self.execucao,
            EventoLog.BLOQUEADO,
            "SKU ME550 bloqueado",
            variacao=variacao,
            nivel=NivelLog.AVISO,
            motivo="SKU já existe no Tiny (id=857279363) e não possui vínculo confirmado",
        )

        d = self.client.get(self._url()).data
        self.assertEqual(d["auditoria"]["bloqueados"], 1)
        self.assertEqual(d["auditoria"]["erros"], 0)
        self.assertEqual(d["auditoria"]["bloqueios_sku_existente_tiny"], 1)
        self.assertIn("sem erro técnico", d["resumo"]["motivo_status"])
        self.assertIn("SKU já existente no Tiny", d["resumo"]["motivo_status"])
        self.assertNotIn("com erro(s)", d["resumo"]["motivo_status"])

    def test_exige_autenticacao(self):
        self.assertEqual(APIClient().get(self._url()).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_execucao_de_outra_instancia_404(self):
        self.assertEqual(
            self.client.get(self._url(instancia=self.outra)).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_execucao_inexistente_404(self):
        self.assertEqual(
            self.client.get(f"/api/instancias/{self.instancia.slug}/execucoes/999999/").status_code,
            status.HTTP_404_NOT_FOUND,
        )


class ExecucaoProdutosTabelaTests(AuditoriaBase):
    def test_xbz_separa_codigo_fornecedor_e_sku_tiny(self):
        variacao = _variacao(
            self.instancia,
            "X134066",
            fornecedor="xbz",
            nome="Caneca térmica 500ml",
            atributos={"codigo_composto": "18700-AZU"},
            payload_bruto={"CodigoComposto": "VALOR-LEGADO"},
        )
        _log(self.execucao, EventoLog.CRIADO, "SKU X134066 criado no Tiny", variacao=variacao, tiny_id="777")

        linha = next(
            l for l in self.client.get(self._url("produtos/")).data["results"] if l["sku"] == "X134066"
        )
        self.assertEqual(linha["codigo_fornecedor"], "X134066")
        self.assertEqual(linha["sku_tiny"], "18700-AZU")
        self.assertNotEqual(linha["sku_tiny"], linha["codigo_fornecedor"])

    def test_uma_linha_por_sku_com_dados_da_variacao(self):
        resp = self.client.get(self._url("produtos/"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 7)
        por_sku = {l["sku"]: l for l in resp.data["results"]}
        self.assertEqual(por_sku["OK-0"]["resultado"], "criado")
        self.assertEqual(por_sku["OK-0"]["tiny_id"], "9000")
        self.assertEqual(por_sku["OK-0"]["produto_nome"], "Caneca 0")
        self.assertEqual(por_sku["OK-0"]["variacao_id"], self.criadas[0].id)
        self.assertEqual(por_sku["VINC-1"]["resultado"], "vinculado")
        self.assertEqual(por_sku["VINC-1"]["tiny_id"], "555")
        self.assertEqual(por_sku["ERR-0"]["resultado"], "erro")
        self.assertIn("descricao obrigatória", por_sku["ERR-0"]["detalhe_curto"])
        self.assertEqual(por_sku["BLOQ-1"]["resultado"], "bloqueado")
        self.assertIn("vínculo confirmado", por_sku["BLOQ-1"]["detalhe_curto"])

    def test_paginacao_no_servidor(self):
        for i in range(60):
            v = _variacao(self.instancia, f"MASS-{i:02d}")
            _log(self.execucao, EventoLog.CRIADO, f"SKU {v.sku} criado no Tiny", variacao=v, tiny_id=f"m{i}")

        p1 = self.client.get(self._url("produtos/"), {"page_size": 25})
        self.assertEqual(p1.data["count"], 67)
        self.assertEqual(len(p1.data["results"]), 25)
        self.assertIsNotNone(p1.data["next"])
        p3 = self.client.get(self._url("produtos/"), {"page_size": 25, "page": 3})
        self.assertEqual(len(p3.data["results"]), 17)

    def test_busca_por_sku_e_nome(self):
        r = self.client.get(self._url("produtos/"), {"busca": "ERR-1"})
        self.assertEqual([l["sku"] for l in r.data["results"]], ["ERR-1"])
        r2 = self.client.get(self._url("produtos/"), {"busca": "Squeeze"})
        self.assertEqual([l["sku"] for l in r2.data["results"]], ["VINC-1"])

    def test_filtro_por_resultado(self):
        erros = self.client.get(self._url("produtos/"), {"resultado": "erros"})
        self.assertEqual(sorted(l["sku"] for l in erros.data["results"]), ["ERR-0", "ERR-1"])
        cadastrados = self.client.get(self._url("produtos/"), {"resultado": "cadastrados"})
        self.assertEqual(
            sorted(l["sku"] for l in cadastrados.data["results"]),
            ["OK-0", "OK-1", "OK-2", "VINC-1"],  # criado + vinculado
        )
        bloq = self.client.get(self._url("produtos/"), {"resultado": "bloqueados"})
        self.assertEqual([l["sku"] for l in bloq.data["results"]], ["BLOQ-1"])

    def test_isolamento_por_instancia(self):
        self.assertEqual(
            self.client.get(self._url("produtos/", instancia=self.outra)).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_retomada_conta_o_desfecho_mais_recente_do_sku(self):
        v = self.com_erro[0]
        v.status = StatusVariacao.CADASTRADO
        v.tiny_id = "999"
        v.save(update_fields=["status", "tiny_id"])
        _log(self.execucao, EventoLog.CRIADO, f"SKU {v.sku} criado no Tiny", variacao=v, tiny_id="999")

        linha = next(
            l for l in self.client.get(self._url("produtos/")).data["results"] if l["sku"] == v.sku
        )
        self.assertEqual(linha["resultado"], "criado")  # não "erro"
        self.assertEqual(linha["tiny_id"], "999")

    def test_imagens_por_sku(self):
        v = self.criadas[0]
        _log(self.execucao, EventoLog.IMAGENS, f"Imagens do SKU {v.sku} enviadas ao Tiny", variacao=v)
        linha = next(l for l in self.client.get(self._url("produtos/")).data["results"] if l["sku"] == v.sku)
        self.assertEqual(linha["imagens"], "ok")


class LogsTecnicosTests(AuditoriaBase):
    def test_escopo_gerais_traz_so_os_logs_sem_sku(self):
        r = self.client.get(self._url("logs/"), {"escopo": "gerais"})
        msgs = [l["mensagem"] for l in r.data["results"]]
        self.assertEqual(len(msgs), 2)
        self.assertIn("Sincronização com o Tiny iniciada", msgs)
        self.assertIn("Sincronização pausada — pode ser retomada", msgs)
        self.assertNotIn("criado no Tiny", " ".join(msgs))

    def test_logs_de_um_sku_para_o_expand_tecnico(self):
        v = self.com_erro[0]
        r = self.client.get(self._url(f"produtos/{v.id}/"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["results"]), 1)
        log = r.data["results"][0]
        self.assertEqual(log["evento"], "erro")
        self.assertIn("descricao obrigatória", log["detalhe"]["erro"])  # JSON técnico preservado


class LogsLegadosSemEventoTests(TestCase):
    """Logs criados ANTES da coluna `evento` (default 'geral') não são
    misclassificados — caem em 'técnicos', não na tabela de produtos. A
    migration é quem reclassifica os determinísticos."""

    def setUp(self):
        self.client = _client()
        self.instancia = Instancia.objects.create(nome="Loja Legada")
        self.execucao = Execucao.objects.create(
            instancia=self.instancia, fornecedor="asia", tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.PARCIAL, total_lidos=2, total_cadastrados=1, total_erros=1,
        )
        v = _variacao(self.instancia, "LEG-1")
        # simula log antigo: sem evento explícito -> default 'geral', mas COM variacao
        LogItem.objects.create(
            execucao=self.execucao, variacao=v, nivel=NivelLog.INFO, mensagem="SKU LEG-1 criado no Tiny",
            detalhe={"tiny_id": "1"},
        )

    def test_log_legado_geral_nao_vira_linha_de_auditoria(self):
        r = self.client.get(f"/api/instancias/{self.instancia.slug}/execucoes/{self.execucao.id}/produtos/")
        self.assertEqual(r.data["count"], 0)  # evento='geral' não é desfecho

    def test_reclassificacao_da_migration_recupera_o_desfecho(self):
        import importlib

        from django.apps import apps as django_apps

        migracao = importlib.import_module(
            "apps.sincronizacao.migrations.0004_logitem_evento_and_more"
        )
        migracao.classificar_logs_existentes(django_apps, None)

        r = self.client.get(f"/api/instancias/{self.instancia.slug}/execucoes/{self.execucao.id}/produtos/")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["resultado"], "criado")
        self.assertEqual(r.data["results"][0]["tiny_id"], "1")
