import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.agente import Contexto, rodar_uma_vez
from agente_email.caixa import CaixaMemoria, ler_mensagem, utf7_imap
from agente_email.config import Configuracao
from agente_email.drive import DriveLocal
from agente_email.estado import Estado
from agente_email.modelos import Mensagem
from agente_email.notificar import NotificadorMemoria, NtfyNotificador, evento_ics
from agente_email.planilha import PlanilhaMemoria

OS = "1111.2222.000000001/2026.01.01"
OSP = OS.replace("/", "")
HOJE = date(2026, 11, 28)
CFG = Configuracao.de_dict({
    "sid": "x", "sht": "Aba", "fmtPasta": "YYYY-MM", "fmtPastaOS": "S{nr}-{atv}-{os}", "txt_name_tpl": "convocacao.txt",
    "subp": [{"nm": "01 - Convocação", "role": "txt"}, {"nm": "02 - Documentos", "role": "docs"}],
    "atv": {"A413": {"v": 466, "p": 6, "d": True}}, "mun": {"Cidade Exemplo": {"v": 15, "polo": "Polo B"}},
})
TXT = (f"Referência: Ordem de Serviço - {OS}\nAtividade: A413  - X\nEndereço.:  JOSE DA SILVA, 10 - CENTRO\n"
       "Cidade/UF: CIDADE EXEMPLO/RJ\nCEP......: 12345-678\nData da Ordem de Serviço......: 26/11/2026\n"
       "Valor previsto do Deslocamento: R$ 3,15\n")


def convocacao(mid="<a@x>"):
    return Mensagem("AG1@CAIXA.GOV.BR", f"Convocação de Ordem da Serviço {OS}", TXT, [("c.txt", TXT.encode())], id=mid, bruto=b"EML")


def montar(tmp_path, mensagens, linhas=None):
    caixa, plan, notif = CaixaMemoria(mensagens), PlanilhaMemoria(linhas or []), NotificadorMemoria()
    ctx = Contexto(caixa, plan, DriveLocal(tmp_path / "Laudos"), notif, CFG, Estado(tmp_path / "estado.json"), {}, hoje=HOJE)
    return ctx, caixa, plan, notif


def test_fluxo_completo_da_nova_demanda(tmp_path):
    ctx, caixa, plan, notif = montar(tmp_path, [("1", convocacao())])
    assert rodar_uma_vez(ctx) == 1
    l = plan.listar()[0]
    assert l["item"] == "1" and l["vd"] == "R$ 3,15" and "Deslocamento especial" in l["mun"]
    pasta = tmp_path / "Laudos" / "2026-11" / "S1-A413-1111222200000000120260101"
    assert (pasta / "01 - Convocação").is_dir() and (pasta / "02 - Documentos").is_dir()
    assert (pasta / "convocacao.txt").read_text() == TXT and (pasta / "01 - Convocação" / "email_convocacao.eml").read_bytes() == b"EML"
    assert caixa.movidas == {"1": "Ordem de Serviço"}
    assert len(notif.enviados) == 1 and notif.enviados[0]["anexo"][0] == "OS1.ics"
    assert "Nova OS 1" in notif.enviados[0]["titulo"]


def test_segunda_rodada_nao_duplica_nem_reavisa(tmp_path):
    ctx, caixa, plan, notif = montar(tmp_path, [("1", convocacao())])
    rodar_uma_vez(ctx)
    caixa.movidas.clear()               # simula e-mail que voltou para a caixa
    rodar_uma_vez(ctx)
    assert len(plan.listar()) == 1 and len(notif.enviados) == 1 and caixa.movidas == {}


def test_falha_no_drive_e_retomada_sem_duplicar(tmp_path):
    ctx, caixa, plan, notif = montar(tmp_path, [("1", convocacao())])
    real = ctx.drive.criar_estrutura
    ctx.drive.criar_estrutura = lambda *a, **k: (_ for _ in ()).throw(OSError("disco cheio"))
    rodar_uma_vez(ctx)
    assert len(plan.listar()) == 1 and caixa.movidas == {} and "Erro" in notif.enviados[-1]["titulo"]
    ctx.drive.criar_estrutura = real
    rodar_uma_vez(ctx)
    assert len(plan.listar()) == 1 and caixa.movidas == {"1": "Ordem de Serviço"}
    assert (tmp_path / "Laudos" / "2026-11" / "S1-A413-1111222200000000120260101").is_dir()


def test_cancelamento_e_conclusao_movem_para_suas_pastas(tmp_path):
    linhas = [{"os": OSP, "item": "5", "st": "Sem vistoria - não agendado", "vos": "R$ 466,00", "vd": "R$ 3,15"}]
    ms = [("1", Mensagem("AG1@CAIXA.GOV.BR", f"Cancelamento da Ordem Serviço {OS}", "", id="<c>")),
          ("2", Mensagem("AG1@CAIXA.GOV.BR", f"Conclusão da Ordem de Serviço {OSP[:0] + OS}", "Valor Efetivo do Serviço.....: R$ 466,00", id="<d>"))]
    ctx, caixa, plan, notif = montar(tmp_path, ms, linhas)
    rodar_uma_vez(ctx)
    assert caixa.movidas == {"1": "Cancelamento OS", "2": "Conclusão OS"}
    assert plan.listar()[0]["st"] == "OS Concluída"


def test_revisao_sem_pasta_definida_nao_move_mas_nao_repete(tmp_path):
    linhas = [{"os": OSP, "item": "5", "st": "OS Concluída", "rev": "FALSE"}]
    m = Mensagem("siopi@caixa.gov.br", "Solicitação de revisão do valor de avaliação", f"da OS {OS}, X", id="<r>")
    ctx, caixa, plan, notif = montar(tmp_path, [("1", m)], linhas)
    ctx.pastas = {**ctx.pastas, "revisao": None}
    rodar_uma_vez(ctx)
    abr = plan.listar()[0]["abr"]
    ctx.hoje = date(2026, 12, 10)
    rodar_uma_vez(ctx)                   # não pode reabrir a revisão com outra data
    assert plan.listar()[0]["abr"] == abr == "28/11/2026" and caixa.movidas == {}
    assert len(notif.enviados) == 1


def test_pept_grava_sinalizacao_na_pasta_da_os(tmp_path):
    pasta = tmp_path / "Laudos" / "2026-11" / "S5-A413-1111222200000000120260101"
    pasta.mkdir(parents=True)
    m = Mensagem("siopi@caixa.gov.br", "Resolução do PEPT da OS", f"pendência aberta para a OS {OS} foi resolvida.", id="<p>")
    ctx, caixa, plan, notif = montar(tmp_path, [("1", m)], [{"os": OSP, "item": "5"}])
    rodar_uma_vez(ctx)
    assert (pasta / "pept_resposta.json").exists() and caixa.movidas == {"1": "Pendências PEPT"}


def test_email_desconhecido_avisa_uma_vez_e_nao_move(tmp_path):
    m = Mensagem("alguem@caixa.gov.br", "Pesquisa de satisfação", "", id="<z>")
    ctx, caixa, plan, notif = montar(tmp_path, [("1", m)])
    rodar_uma_vez(ctx); rodar_uma_vez(ctx)
    assert caixa.movidas == {} and len(notif.enviados) == 1 and plan.listar() == []


def test_utf7_das_pastas():
    assert utf7_imap("Conclusão OS") == "Conclus&AOM-o OS"
    assert utf7_imap("Ordem de Serviço") == "Ordem de Servi&AOc-o"
    assert utf7_imap("A&B") == "A&-B"


def test_ler_mensagem_imap_com_anexo_e_assunto_codificado():
    from email.message import EmailMessage
    e = EmailMessage()
    e["From"], e["To"], e["Message-ID"] = "AG0197@CAIXA.GOV.BR", "x@y.com", "<abc@caixa>"
    e["Subject"] = f"Convocação de Ordem da Serviço {OS}"
    e.set_content(TXT)
    e.add_attachment(TXT.encode("cp1252"), maintype="text", subtype="plain", filename="C.txt")
    m = ler_mensagem(e.as_bytes(), "7")
    assert m.assunto.startswith("Convocação") and m.id == "<abc@caixa>" and m.anexos[0][0] == "C.txt" and m.bruto


def test_ntfy_e_agenda():
    chamadas = []
    n = NtfyNotificador("https://ntfy.sh", "topico", http=lambda *a: chamadas.append(a))
    n.enviar("Nova OS", "texto ç", "high")
    n.enviar("Nova OS ç", "texto", anexo=("OS1.ics", b"x"))
    assert chamadas[0][0] == "POST" and b"texto \xc3\xa7" in chamadas[0][3]
    assert chamadas[1][0] == "PUT" and chamadas[1][2]["Title"] == "Nova OS c"
    ics = evento_ics(OS, "Entrega", date(2026, 12, 2)).decode()
    assert "DTSTART;VALUE=DATE:20261202" in ics and "TRIGGER:-PT15H" in ics and "TRIGGER:PT8H" in ics


def test_candidatos_e_nomes_de_pasta():
    from agente_email.caixa import candidatos_servidor, decodificar_pasta
    assert candidatos_servidor("a@x.com.br") == ["mail.x.com.br", "imap.x.com.br", "x.com.br"]
    assert candidatos_servidor("a@x.com.br", "br1.host.com")[0] == "br1.host.com"
    assert decodificar_pasta(b'(\\HasNoChildren) "." "Conclus&AOM-o OS"') == "Conclusão OS"
    assert decodificar_pasta(b'(\\HasNoChildren) "." INBOX') == "INBOX"


def test_resolver_pasta_usa_a_existente_com_prefixo_inbox():
    from agente_email.caixa import resolver_pasta, separar_list
    nomes = ["INBOX", "INBOX.Sent", "INBOX.Ordem de Serviço", "INBOX.Conclusao OS"]
    assert resolver_pasta(nomes, ".", "Ordem de Serviço") == "INBOX.Ordem de Serviço"
    assert resolver_pasta(nomes, ".", "Conclusão OS") == "INBOX.Conclusao OS"          # ignora acento
    assert resolver_pasta(nomes, ".", "Pendências PEPT") == "INBOX.Pendências PEPT"    # cria dentro de INBOX.
    assert resolver_pasta(["INBOX", "Sent"], "/", "Pendências PEPT") == "Pendências PEPT"
    assert separar_list(b'(\\HasNoChildren) "." "INBOX.Ordem de Servi&AOc-o"') == (".", "INBOX.Ordem de Serviço")
    assert separar_list(b'(\\HasNoChildren) "." INBOX.Sent') == (".", "INBOX.Sent")


def test_data_do_email_e_lida():
    from email.message import EmailMessage
    from agente_email.caixa import ler_mensagem
    e = EmailMessage()
    e["From"], e["Subject"], e["Date"] = "a@caixa.gov.br", "x", "Fri, 27 Nov 2026 09:45:29 -0300"
    e.set_content("c")
    assert ler_mensagem(e.as_bytes()).data.date() == date(2026, 11, 27)


def test_revisao_vai_para_a_pasta_revisao_os_por_padrao(tmp_path):
    linhas = [{"os": OSP, "item": "5", "st": "OS Concluída", "rev": "FALSE"}]
    m = Mensagem("siopi@caixa.gov.br", "Solicitação de revisão do valor de avaliação", f"da OS {OS}, X", id="<r2>")
    ctx, caixa, plan, notif = montar(tmp_path, [("1", m)], linhas)
    rodar_uma_vez(ctx)
    assert caixa.movidas == {"1": "Revisão OS"}


def test_resolver_pasta_real_do_usuario():
    from agente_email.caixa import resolver_pasta
    nomes = ["INBOX", "INBOX.Pendências PEPT", "INBOX.Conclusão OS", "INBOX.Ordem de Serviço", "INBOX.Archive",
             "INBOX.Archive.Cancelamento OS", "INBOX.Archive.Revisão OS", "INBOX.Trash", "INBOX.Trash.Revisão"]
    assert resolver_pasta(nomes, ".", "Revisão OS") == "INBOX.Archive.Revisão OS"
    assert resolver_pasta(nomes, ".", "Cancelamento OS") == "INBOX.Archive.Cancelamento OS"
