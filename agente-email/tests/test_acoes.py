import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.acoes import aplicar
from agente_email.classificador import classificar
from agente_email.modelos import Mensagem
from agente_email.planilha import PlanilhaMemoria, letra_coluna

OS = "1111.2222.000000001/2026.01.01"
OSP = OS.replace("/", "")
HOJE = date(2026, 11, 28)
REGRAS = {"revisao": {"prazo_dias_corridos": 6}}


def planilha(**extra):
    base = {"os": OSP, "st": "Sem vistoria - não agendado", "vos": "R$ 466,00", "vd": "R$ 8,40", "vt": "R$ 474,40", "rev": "FALSE"}
    base.update(extra)
    return PlanilhaMemoria([base])


def email(assunto, corpo="", remetente="AG1@CAIXA.GOV.BR"):
    m = Mensagem(remetente, assunto, corpo)
    return m, classificar(m)


def test_letra_coluna():
    assert [letra_coluna(i) for i in (0, 25, 26, 29)] == ["A", "Z", "AA", "AD"]


def test_conclusao_muda_status_e_nao_avisa_se_valores_iguais():
    p = planilha()
    m, c = email(f"Conclusão da Ordem de Serviço {OS}", "Valor Efetivo do Serviço.....: R$ 466,00\nValor Efetivo do Deslocamento: R$ 8,40")
    r = aplicar(c, m, p, REGRAS, HOJE)
    assert r.aplicado and r.pode_mover_email and not r.avisos
    assert p.listar()[0]["st"] == "OS Concluída"


def test_conclusao_avisa_divergencia_de_valor():
    p = planilha()
    m, c = email(f"Conclusão da Ordem de Serviço {OS}", "Valor Efetivo do Serviço.....: R$ 500,00\nValor Efetivo do Deslocamento: R$ 8,40")
    r = aplicar(c, m, p, REGRAS, HOJE)
    assert r.aplicado and any("serviço diverge" in a for a in r.avisos)


def test_cancelamento_zera_valores_como_o_dashboard():
    p = planilha()
    m, c = email(f"Cancelamento da Ordem Serviço {OS}")
    r = aplicar(c, m, p, REGRAS, HOJE)
    l = p.listar()[0]
    assert (l["st"], l["vos"], l["vd"], l["vt"]) == ("OS Cancelada", "R$ 0,00", "R$ 0,00", "R$ 0,00")
    assert not r.avisos


def test_cancelamento_com_servico_ja_feito_avisa():
    p = planilha(vis="TRUE")
    m, c = email(f"Cancelamento da Ordem Serviço {OS}")
    assert any("JÁ TINHA serviço" in a for a in aplicar(c, m, p, REGRAS, HOJE).avisos)


def test_revisao_abre_prazo_de_6_dias_corridos():
    p = planilha()
    m, c = email("Solicitação de revisão do valor de avaliação", f"revisão do valor de avaliação da OS {OS}, FULANO", "siopi@caixa.gov.br")
    r = aplicar(c, m, p, REGRAS, HOJE)
    l = p.listar()[0]
    assert (l["st"], l["rev"], l["abr"], l["prz"]) == ("OS em Revisão", "TRUE", "28/11/2026", "04/12/2026")
    assert r.pode_mover_email


def test_pept_so_sinaliza_e_nao_mexe_na_planilha():
    p = planilha()
    antes = p.listar()
    m, c = email("Resolução do PEPT da OS", f"pendência aberta para a OS {OS} foi resolvida.", "siopi@caixa.gov.br")
    r = aplicar(c, m, p, REGRAS, HOJE)
    assert p.listar() == antes and r.arquivos == ["pept_resposta.json"] and r.avisos


def test_os_inexistente_ou_duplicada_nao_altera_e_nao_move():
    m, c = email(f"Cancelamento da Ordem Serviço {OS}")
    r = aplicar(c, m, PlanilhaMemoria([]), REGRAS, HOJE)
    assert not r.aplicado and not r.pode_mover_email
    dup = PlanilhaMemoria([{"os": OSP}, {"os": OSP}])
    assert not aplicar(c, m, dup, REGRAS, HOJE).aplicado


def test_email_nao_confiavel_nao_age():
    m, c = email("Cancelamento da Ordem Serviço sem numero")
    assert not aplicar(c, m, planilha(), REGRAS, HOJE).aplicado
