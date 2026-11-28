import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.agenda import AgendaIcloud, AgendaMemoria, chave
from agente_email.agente import rodar_uma_vez
from agente_email.modelos import Mensagem
from tests.test_fluxo import HOJE, OS, OSP, convocacao, montar


class Resp:
    def __init__(self, status=200, texto="", cab=None):
        self.status_code, self.text, self.headers = status, texto, cab or {}


class IcloudFalso:
    """Servidor CalDAV mínimo: descoberta, MKCALENDAR, PUT e DELETE."""
    def __init__(self, ja_tem_calendario=False, redireciona=False):
        self.eventos, self.chamadas, self.calendarios = {}, [], {}
        self.redireciona = redireciona
        if ja_tem_calendario:
            self.calendarios["/123/calendars/abc/"] = "Entregas OS"

    def request(self, metodo, url, data=None, headers=None, auth=None, timeout=None, allow_redirects=True):
        self.chamadas.append((metodo, url))
        assert auth == ("eu@icloud.com", "senha-app") and allow_redirects is False
        if url == "https://caldav.icloud.com/" and self.redireciona and not hasattr(self, "_r"):
            self._r = True
            return Resp(301, cab={"Location": "https://p01-caldav.icloud.com/"})
        host = "https://p01-caldav.icloud.com" if self.redireciona else "https://caldav.icloud.com"
        if metodo == "PROPFIND" and b"current-user-principal" in data:
            return Resp(207, '<d:multistatus xmlns:d="DAV:"><d:response><d:propstat><d:prop><d:current-user-principal><d:href>/123/principal/</d:href>'
                             '</d:current-user-principal></d:prop></d:propstat></d:response></d:multistatus>')
        if metodo == "PROPFIND" and b"calendar-home-set" in data:
            return Resp(207, f'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response><d:propstat><d:prop><c:calendar-home-set>'
                             f'<d:href>{host}:443/123/calendars/</d:href></c:calendar-home-set></d:prop></d:propstat></d:response></d:multistatus>')
        if metodo == "PROPFIND":
            itens = "".join(f'<d:response><d:href>{h}</d:href><d:propstat><d:prop><d:displayname>{n}</d:displayname>'
                            f'<d:resourcetype><d:collection/><c:calendar/></d:resourcetype></d:prop></d:propstat></d:response>'
                            for h, n in self.calendarios.items())
            itens += '<d:response><d:href>/123/calendars/inbox/</d:href><d:propstat><d:prop><d:displayname>Caixa</d:displayname><d:resourcetype/></d:prop></d:propstat></d:response>'
            return Resp(207, f'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">{itens}</d:multistatus>')
        if metodo == "MKCALENDAR":
            self.calendarios[url.replace("https://p01-caldav.icloud.com:443", "").replace("https://caldav.icloud.com:443", "")] = "Entregas OS"
            return Resp(201)
        if metodo == "PUT":
            self.eventos[url.rsplit("/", 1)[1]] = data.decode()
            return Resp(201)
        if metodo == "DELETE":
            return Resp(204) if self.eventos.pop(url.rsplit("/", 1)[1], None) else Resp(404)
        return Resp(500)


def op(ch="os-1", dia="2026-12-02", titulo="Entrega OS 1"):
    return {"acao": "salvar", "chave": ch, "dia": dia, "titulo": titulo, "local": "Rua X, Centro", "descricao": "OS 1\nvalor"}


def test_cria_calendario_se_nao_existe_e_grava_evento():
    srv = IcloudFalso()
    ag = AgendaIcloud("eu@icloud.com", "senha-app", sessao=srv)
    ag.executar(op())
    assert any(m == "MKCALENDAR" for m, _ in srv.chamadas)
    ics = srv.eventos["os-1.ics"]
    assert "DTSTART;VALUE=DATE:20261202" in ics and "SUMMARY:Entrega OS 1" in ics and "LOCATION:Rua X\\, Centro" in ics


def test_reaproveita_calendario_existente_e_segue_redirecionamento():
    srv = IcloudFalso(ja_tem_calendario=True, redireciona=True)
    ag = AgendaIcloud("eu@icloud.com", "senha-app", sessao=srv)
    ag.executar(op())
    assert not any(m == "MKCALENDAR" for m, _ in srv.chamadas) and "os-1.ics" in srv.eventos
    n = len(srv.chamadas)
    ag.executar(op(titulo="Novo título"))                 # a descoberta não se repete
    assert len(srv.chamadas) == n + 1 and "Novo título" in srv.eventos["os-1.ics"]


def test_remover_e_idempotente():
    srv = IcloudFalso(ja_tem_calendario=True)
    ag = AgendaIcloud("eu@icloud.com", "senha-app", sessao=srv)
    ag.executar(op())
    ag.executar({"acao": "remover", "chave": "os-1"})
    ag.executar({"acao": "remover", "chave": "os-1"})      # já não existe: 404 não é erro
    assert "os-1.ics" not in srv.eventos


def test_senha_errada_da_erro_claro():
    class Recusa(IcloudFalso):
        def request(self, *a, **k):
            return Resp(401)
    try:
        AgendaIcloud("eu@icloud.com", "senha-app", sessao=Recusa()).executar(op())
        assert False
    except PermissionError as e:
        assert "senha de aplicativo" in str(e)


def com_agenda(tmp_path, mensagens, linhas=None):
    ctx, caixa, plan, notif = montar(tmp_path, mensagens, linhas)
    ctx.agenda = AgendaMemoria()
    return ctx, caixa, plan, notif


def test_nova_os_cria_compromisso_sem_anexo_ics(tmp_path):
    ctx, caixa, plan, notif = com_agenda(tmp_path, [("1", convocacao())])
    rodar_uma_vez(ctx)
    ev = ctx.agenda.eventos[chave(OS)]
    assert ev["dia"] == "2026-12-02" and ev["titulo"].startswith("Entrega OS 1 · A413")
    assert notif.enviados[0]["anexo"] is None and "agenda atualizada" in notif.enviados[0]["texto"]


def test_conclusao_e_cancelamento_removem_compromissos(tmp_path):
    ctx, caixa, plan, notif = com_agenda(tmp_path, [("1", convocacao())])
    rodar_uma_vez(ctx)
    assert chave(OS) in ctx.agenda.eventos
    ctx.caixa.mensagens.append(("2", Mensagem("AG1@CAIXA.GOV.BR", f"Cancelamento da Ordem Serviço {OS}", "", id="<c>")))
    rodar_uma_vez(ctx)
    assert ctx.agenda.eventos == {}


def test_revisao_cria_compromisso_do_prazo(tmp_path):
    linhas = [{"os": OSP, "item": "5", "st": "OS Concluída", "rev": "FALSE", "mun": "X"}]
    m = Mensagem("siopi@caixa.gov.br", "Solicitação de revisão do valor de avaliação", f"da OS {OS}, X", id="<r>")
    ctx, caixa, plan, notif = com_agenda(tmp_path, [("1", m)], linhas)
    rodar_uma_vez(ctx)
    ev = ctx.agenda.eventos[chave(OS, "rev")]
    assert ev["dia"] == "2026-12-04" and "Revisão OS 5" in ev["titulo"]


def test_falha_no_icloud_nao_trava_e_tenta_de_novo(tmp_path):
    ctx, caixa, plan, notif = com_agenda(tmp_path, [("1", convocacao())])
    ctx.agenda.falhar = True
    for _ in range(3):
        rodar_uma_vez(ctx)
    assert len(plan.listar()) == 1 and caixa.movidas == {"1": "Ordem de Serviço"}    # a OS foi tratada normalmente
    assert ctx.agenda.eventos == {} and any("Agenda do iCloud" in n["titulo"] for n in notif.enviados)
    ctx.agenda.falhar = False
    rodar_uma_vez(ctx)
    assert chave(OS) in ctx.agenda.eventos
