import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.classificador import classificar
from agente_email.convocacao import interpretar
from agente_email.eventos import interpretar_conclusao
from agente_email.modelos import Mensagem
from agente_email.texto import reparar_mojibake

OS = "1111.2222.000000001/2026.01.01"
OS2 = "3333.4444.000000002/2026.01.01"


def msg(assunto, corpo="", remetente="AG9999@CAIXA.GOV.BR"):
    return Mensagem(remetente, assunto, corpo)


def test_convocacao_com_erro_de_digitacao_da_cef():
    c = classificar(msg(f"Convocação de Ordem da Serviço {OS}"))
    assert (c.tipo, c.os_numero, c.confiavel) == ("convocacao", OS, True)


def test_conclusao_e_cancelamento_variacoes():
    assert classificar(msg(f"Conclusão da Ordem de Serviço {OS}")).tipo == "conclusao"
    assert classificar(msg(f"Cancelamento da Ordem Serviço {OS}")).tipo == "cancelamento"
    assert classificar(msg(f"Cancelamento da Ordem de Serviço {OS}")).tipo == "cancelamento"


def test_revisao_e_pept_leem_a_os_no_corpo():
    c = classificar(msg("Solicitação de revisão do valor de avaliação",
                        f"1 - Foi solicitada revisão do valor de avaliação da OS {OS}, FULANO", "siopi@caixa.gov.br"))
    assert (c.tipo, c.os_numero) == ("revisao", OS)
    c = classificar(msg("Resolução do PEPT da OS", f"A pendência aberta para a OS {OS2} foi resolvida.", "siopi@caixa.gov.br"))
    assert (c.tipo, c.os_numero) == ("pept", OS2)


def test_assunto_com_mojibake_e_caracter_perdido():
    assert classificar(msg(f"ConvocaÃ§Ã£o de Ordem da ServiÃ§o {OS}")).tipo == "convocacao"
    assert classificar(msg(f"Conclus��o da Ordem de Servi�o {OS}")).tipo == "conclusao"


def test_remetente_fora_da_caixa_nao_age():
    c = classificar(msg(f"Cancelamento da Ordem Serviço {OS}", remetente="golpe@outro.com"))
    assert c.tipo == "desconhecido" and not c.confiavel


def test_assunto_desconhecido_nao_age():
    assert not classificar(msg("Reunião amanhã")).confiavel


def test_os_ausente_ou_divergente_nao_age():
    assert not classificar(msg("Conclusão da Ordem de Serviço sem numero")).confiavel
    assert not classificar(msg(f"Conclusão da Ordem de Serviço {OS}", f"OS {OS2}")).confiavel


def test_pept_sem_os_no_corpo_nao_age():
    assert not classificar(msg("Resolução do PEPT da OS", "sem número", "siopi@caixa.gov.br")).confiavel


TXT = f"""
Referência: Ordem de Serviço - {OS}
Atividade: A413  - AVALIACAO VISTORIA
Imóvel ..: CIDADE EXEMPLO/RJ
           Matrícula RGI: 123, Ofício: 01
Endereço.:  JOSE DA SILVA, 10 - CENTRO
Cidade/UF: CIDADE EXEMPLO/RJ
CEP......: 12345-678
Data da Ordem de Serviço......: 26/11/2026
Prazo de execução.............:   6 Dia(s) corridos.
Valor previsto do Serviço.....: R$ 466,00
Valor previsto do Deslocamento: R$ 3,15
Nome do contato.: MARIA
Telefone contato: (21)99999-0000
Endereço: RUA DO DEMANDANTE, 1
CEP: 99999-999
"""


def test_convocacao_campos_iguais_ao_dashboard():
    d = interpretar(TXT)
    assert d["os"] == OS
    assert d["endereco"] == "Rua José da Silva, 10".replace("José", "Jose")
    assert d["bairro"] == "Centro"
    assert (d["municipio"], d["uf"], d["cep"]) == ("Cidade Exemplo", "RJ", "12345-678")
    assert (d["atividade"], d["data_os"], d["prazo_dias"]) == ("A413", "26/11/2026", "6")
    assert (d["valor_servico"], d["valor_deslocamento"]) == ("466,00", "3,15")
    assert d["matricula"] == "123"


def test_convocacao_com_texto_corrompido():
    ruim = TXT.replace("Endereço", "EndereÃ§o").replace("Serviço", "ServiÃ§o").replace("Matrícula", "MatrÃ\xadcula")
    assert interpretar(ruim)["endereco"] == "Rua Jose da Silva, 10"
    assert interpretar(ruim)["matricula"] == "123"


def test_conclusao_valores_efetivos():
    corpo = "Data de Conclusão: 27/11/2026\nValor Efetivo do ServiÃ§O.....: R$ 466,00\nValor Efetivo do Deslocamento: R$ 8,40"
    d = interpretar_conclusao(corpo)
    assert d == {"data_conclusao": "27/11/2026", "valor_servico": "466,00", "valor_deslocamento": "8,40"}


def test_mojibake_nao_estraga_texto_legitimo():
    assert reparar_mojibake("SÃO PAULO") == "SÃO PAULO"
    assert reparar_mojibake("São Paulo") == "São Paulo"
    assert reparar_mojibake("ConvocaÃ§Ã£o") == "Convocação"
