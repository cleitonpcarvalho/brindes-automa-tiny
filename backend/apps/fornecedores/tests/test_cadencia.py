from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.instancias.models import CredencialFornecedor, Instancia

from ..models import CadenciaFornecedor


class CadenciaMinimaXbzTests(TestCase):
    """Regra do cliente: xbz nunca pode sincronizar mais que 1x/hora (limite de 24 chamadas/dia)."""

    def test_xbz_com_intervalo_menor_que_60_minutos_e_recusado(self):
        instancia = Instancia.objects.create(nome="Loja Cadencia")
        with self.assertRaises(ValidationError):
            CadenciaFornecedor.objects.create(instancia=instancia, fornecedor="xbz", intervalo_minutos=30)

    def test_xbz_com_60_minutos_ou_mais_e_aceito(self):
        instancia = Instancia.objects.create(nome="Loja Cadencia 2")
        cadencia = CadenciaFornecedor.objects.create(
            instancia=instancia, fornecedor="xbz", intervalo_minutos=120
        )
        self.assertEqual(cadencia.intervalo_minutos, 120)

    def test_outros_fornecedores_podem_ser_mais_frequentes_que_60_minutos(self):
        instancia = Instancia.objects.create(nome="Loja Cadencia 3")
        cadencia = CadenciaFornecedor.objects.create(
            instancia=instancia, fornecedor="asia", intervalo_minutos=15
        )
        self.assertEqual(cadencia.intervalo_minutos, 15)


class CadenciaPadraoAoCriarCredencialTests(TestCase):
    def test_criar_credencial_gera_cadencia_padrao_de_60_minutos(self):
        instancia = Instancia.objects.create(nome="Loja com Credencial")
        CredencialFornecedor.objects.create(instancia=instancia, fornecedor="spot", credenciais={})

        cadencia = CadenciaFornecedor.objects.get(instancia=instancia, fornecedor="spot")
        self.assertEqual(cadencia.intervalo_minutos, 60)
        self.assertTrue(cadencia.ativo)
