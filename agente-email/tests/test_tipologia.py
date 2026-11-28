import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.config import Configuracao
from agente_email.convocacao import interpretar
from agente_email.criar_os import montar
from agente_email.siopi import TIPOLOGIAS_PADRAO, campos_planilha
from agente_email.tipologia import e_acompanhamento_de_obra, inferir

OS = "1111.2222.000000001/2026.01.01"
CFG = Configuracao.de_dict({"sid": "x", "sht": "A", "fmtPasta": "YYYY-MM", "fmtPastaOS": "S{nr}-{atv}-{os}",
                            "atv": {"E401": {"v": 700, "p": 6, "d": True}, "A413": {"v": 466, "p": 6, "d": True}},
                            "mun": {"Cidade Exemplo": {"v": 15, "polo": "B"}}})


def txt(atv, descricao="", assunto=""):
    return (f"Referência: Ordem de Serviço - {OS}\nAtividade: {atv} - X\nAssunto .: {assunto}\nEndereço.:  JOSE DA SILVA, 10 - CENTRO\n"
            f"Cidade/UF: CIDADE EXEMPLO/RJ\nCEP......: 12345-678\nData da Ordem de Serviço......: 26/11/2026\n"
            f"Valor previsto do Deslocamento: R$ 15,00\nDescrição: {descricao}\n\n")


def tip_de(t):
    return montar(interpretar(t), CFG, [], date(2026, 11, 28))[0]


def test_reconhece_acompanhamento_de_obra():
    assert e_acompanhamento_de_obra("E401") and e_acompanhamento_de_obra("E-401") and not e_acompanhamento_de_obra("A413")


def test_descricao_com_obra_residencial():
    o = tip_de(txt("E401", descricao="ACOMPANHAMENTO DE OBRA RESIDENCIAL"))
    assert o.campos["tip"] == "Obra Residencial" and not o.avisos


def test_descricao_so_residencial():
    assert tip_de(txt("E401", descricao="Unifamiliar residencial")).campos["tip"] == "Obra Residencial"


def test_obra_sem_dica_assume_obra_residencial_e_avisa():
    o = tip_de(txt("E401", descricao="medicao 3"))
    assert o.campos["tip"] == "Obra Residencial" and any("assumida" in a for a in o.avisos)


def test_outras_atividades_usam_o_nome_da_opcao_no_texto_ou_ficam_vazias():
    assert tip_de(txt("A413", descricao="Apartamento no centro")).campos["tip"] == "Apartamento"
    assert tip_de(txt("A413", descricao="financ")).campos["tip"] == ""


def test_siopi_nao_troca_a_tipologia_de_obra():
    novos, _ = campos_planilha({"tipo_construcao": "Casa"}, {"atv": "E401", "tip": "Obra Residencial", "mun": "Cidade Exemplo"})
    assert "tip" not in novos
    novos, _ = campos_planilha({"tipo_construcao": "Casa"}, {"atv": "A413", "tip": "", "mun": "Cidade Exemplo"})
    assert novos["tip"] == "Casa"


def test_inferir_direto():
    assert inferir("loja térrea", "A413", TIPOLOGIAS_PADRAO)[0] == "Loja"
