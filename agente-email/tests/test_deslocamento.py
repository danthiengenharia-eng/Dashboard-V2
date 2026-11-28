import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.deslocamento import achar_municipio, identificar, valor_especial

MUN = {"Rio De Janeiro": {"v": 40.0, "polo": "A"}, "Cidade Exemplo": {"v": 15.0, "polo": "B"}}


def test_valor_especial_e_21_por_cento_arredondado():
    assert valor_especial(40.0) == 8.40
    assert valor_especial(15.0) == 3.15
    assert valor_especial(33.33) == 7.0  # 6.9993 -> 7.00


def test_rio_padrao_e_especial():
    assert identificar("Rio de Janeiro", {"txt": 40.0}, MUN).especial is False
    r = identificar("RIO DE JANEIRO", {"txt": 8.40}, MUN)
    assert r.especial is True and r.campo == "Sim"
    assert r.municipio_para_gravar == "Rio De Janeiro (Deslocamento especial)"


def test_municipio_normal_grava_so_o_nome():
    r = identificar("Cidade Exemplo", {"txt": 15.0}, MUN)
    assert r.campo == "Não" and r.municipio_para_gravar == "Cidade Exemplo"


def test_valor_fora_do_padrao_nao_decide():
    r = identificar("Rio de Janeiro", {"txt": 12.0}, MUN)
    assert r.especial is None and r.campo == "Indefinido" and r.avisos


def test_fontes_divergentes_nao_decidem():
    r = identificar("Rio de Janeiro", {"txt": 8.40, "siopi": 40.0}, MUN)
    assert r.especial is None and any("divergem" in a for a in r.avisos)


def test_fontes_concordantes_decidem():
    assert identificar("Rio de Janeiro", {"txt": 8.40, "siopi": 8.40}, MUN).especial is True


def test_fonte_ausente_usa_a_outra():
    assert identificar("Rio de Janeiro", {"txt": None, "siopi": 8.40}, MUN).especial is True


def test_municipio_fora_da_configuracao_avisa():
    r = identificar("Lugar Nenhum", {"txt": 5.0}, MUN)
    assert r.especial is None and r.avisos


def test_sem_valor_em_nenhuma_fonte_avisa():
    assert identificar("Rio de Janeiro", {}, MUN).especial is None


def test_nome_com_sufixo_e_acento():
    assert achar_municipio("Rio de Janeiro (Deslocamento especial)", MUN) == "Rio De Janeiro"
