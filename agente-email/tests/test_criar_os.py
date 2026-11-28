import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.acoes import aplicar
from agente_email.classificador import classificar
from agente_email.config import Configuracao, mes_abreviado, mes_para_pasta, nome_pasta_os
from agente_email.modelos import Mensagem
from agente_email.planilha import PlanilhaMemoria

OS = "1111.2222.000000001/2026.01.01"
HOJE = date(2026, 11, 28)
CFG = Configuracao.de_dict({
    "sid": "x", "sht": "Aba", "cols": {}, "fmtPasta": "YYYY-MM", "fmtPastaOS": "S{nr}-{atv}-{os}",
    "atv": {"A413": {"v": 466, "p": 6, "d": True}, "G402": {"v": 300, "p": 5, "d": False}},
    "mun": {"Rio De Janeiro": {"v": 40, "polo": "Rio De Janeiro"}, "Cidade Exemplo": {"v": 15, "polo": "Polo B"}},
})


def txt(mun="CIDADE EXEMPLO", desloc="3,15", atv="A413", extra=""):
    return (f"Referência: Ordem de Serviço - {OS}\nAtividade: {atv}  - AVALIACAO\nEndereço.:  JOSE DA SILVA, 10 - CENTRO\n"
            f"Cidade/UF: {mun}/RJ\nCEP......: 12345-678\nData da Ordem de Serviço......: 26/11/2026\n"
            f"Valor previsto do Deslocamento: R$ {desloc}\n{extra}")


def conv(t=None, anexo=True):
    t = t or txt()
    m = Mensagem("AG1@CAIXA.GOV.BR", f"Convocação de Ordem da Serviço {OS}", t, [("c.txt", t.encode("utf-8"))] if anexo else [])
    return m, classificar(m)


def test_formatos_de_nome_iguais_ao_dashboard():
    assert mes_abreviado(HOJE) == "nov-26"
    assert mes_para_pasta("nov-26", "YYYY-MM") == "2026-11"
    assert nome_pasta_os(1496, "A413", "7903.4018.001247491/2026.01.01", "S{nr}-{atv}-{os}") == "S1496-A413-7903401800124749120260101"


def test_cria_os_com_deslocamento_especial():
    p = PlanilhaMemoria([{"os": "9999.0000.000000009/2026.01.01".replace("/", ""), "item": "1495"}])
    m, c = conv()
    r = aplicar(c, m, p, {}, HOJE, CFG)
    assert r.aplicado and r.pode_mover_email and not r.avisos
    l = p.listar()[-1]
    assert l["item"] == "1496" and l["mun"] == "Cidade Exemplo (Deslocamento especial)" and l["polo"] == "Polo B"
    assert (l["vos"], l["vd"], l["vt"]) == ("R$ 466,00", "R$ 3,15", "R$ 469,15")
    assert (l["siopi"], l["ent"], l["mes"], l["st"]) == ("26/11/2026", "02/12/2026", "nov-26", "Sem vistoria - não agendado")
    assert r.nova_os.pasta_os == "S1496-A413-1111222200000000120260101" and r.nova_os.pasta_mes == "2026-11"
    assert l["os"] == OS.replace("/", "")


def test_deslocamento_padrao_nao_marca_especial():
    p = PlanilhaMemoria([])
    m, c = conv(txt(mun="RIO DE JANEIRO", desloc="40,00"))
    aplicar(c, m, p, {}, HOJE, CFG)
    l = p.listar()[0]
    assert l["mun"] == "Rio De Janeiro" and l["vd"] == "R$ 40,00" and l["item"] == "1"


def test_deslocamento_estranho_cria_mas_avisa():
    p = PlanilhaMemoria([])
    m, c = conv(txt(mun="RIO DE JANEIRO", desloc="12,00"))
    r = aplicar(c, m, p, {}, HOJE, CFG)
    assert r.aplicado and any("DESLOCAMENTO A CONFERIR" in a for a in r.avisos)
    assert p.listar()[0]["vd"] == "R$ 40,00"


def test_atividade_sem_deslocamento_zera():
    p = PlanilhaMemoria([])
    m, c = conv(txt(atv="G402", desloc="0,00"))
    aplicar(c, m, p, {}, HOJE, CFG)
    l = p.listar()[0]
    assert (l["vd"], l["vt"]) == ("R$ 0,00", "R$ 300,00")


def test_nao_duplica_os():
    p = PlanilhaMemoria([{"os": OS.replace("/", ""), "item": "1"}])
    m, c = conv()
    r = aplicar(c, m, p, {}, HOJE, CFG)
    assert not r.aplicado and len(p.listar()) == 1


def test_atividade_ou_municipio_desconhecido_nao_cria():
    for t in (txt(atv="Z999"), txt(mun="LUGAR NENHUM")):
        p = PlanilhaMemoria([])
        m, c = conv(t)
        r = aplicar(c, m, p, {}, HOJE, CFG)
        assert not r.aplicado and not r.pode_mover_email and p.listar() == []


def test_sem_configuracao_nao_cria():
    m, c = conv()
    assert not aplicar(c, m, PlanilhaMemoria([]), {}, HOJE, None).aplicado
