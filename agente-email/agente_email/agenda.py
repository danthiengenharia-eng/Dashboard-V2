"""Compromissos na agenda do iPhone/Mac via iCloud (CalDAV), sem tocar em nada: o agente cria, atualiza e remove.

Usa uma senha de aplicativo do Apple ID (nunca a senha da conta). Cria um calendário próprio ("Entregas OS"),
para que dê para ocultar, colorir ou apagar tudo de uma vez.
"""
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

from .notificar import evento_ics

DAV, CAL = "{DAV:}", "{urn:ietf:params:xml:ns:caldav}"
XML = {"Content-Type": "application/xml; charset=utf-8"}


def chave(os_numero: str, prefixo: str = "os") -> str:
    return f"{prefixo}-{re.sub(r'[^0-9]', '', os_numero)}"


# ---------- operações (serializáveis, para a fila de tentativas) ----------
def ops_nova_os(os_numero: str, campos: dict) -> List[dict]:
    if not campos.get("ent"):
        return []
    dia = datetime.strptime(campos["ent"], "%d/%m/%Y").date().isoformat()
    mun = campos["mun"].replace(" (Deslocamento especial)", "")
    return [{"acao": "salvar", "chave": chave(os_numero), "dia": dia,
             "titulo": f"Entrega OS {campos['item']} · {campos['atv']} · {mun}",
             "local": f"{campos['end']}, {campos['bairro']}, {mun}",
             "descricao": f"OS {os_numero}\\n{campos['end']}, {campos['bairro']} - {mun}\\nValor {campos['vt']}"}]


def ops_encerrar(os_numero: str) -> List[dict]:
    return [{"acao": "remover", "chave": chave(os_numero, p)} for p in ("os", "rev")]


def ops_revisao(os_numero: str, linha: dict, prazo: str) -> List[dict]:
    dia = datetime.strptime(prazo, "%d/%m/%Y").date().isoformat()
    return [{"acao": "salvar", "chave": chave(os_numero, "rev"), "dia": dia,
             "titulo": f"Revisão OS {linha.get('item', '')}: prazo", "local": "",
             "descricao": f"Revisão do valor de avaliação da OS {os_numero}"}]


# ---------- destinos ----------
class Agenda:
    def salvar(self, op: dict) -> None:
        raise NotImplementedError

    def remover(self, chave_evento: str) -> None:
        raise NotImplementedError

    def executar(self, op: dict) -> None:
        if op["acao"] == "salvar":
            self.salvar(op)
        else:
            self.remover(op["chave"])


class AgendaMemoria(Agenda):
    def __init__(self):
        self.eventos: Dict[str, dict] = {}
        self.falhar = False

    def salvar(self, op):
        if self.falhar:
            raise OSError("agenda indisponível")
        self.eventos[op["chave"]] = op

    def remover(self, chave_evento):
        if self.falhar:
            raise OSError("agenda indisponível")
        self.eventos.pop(chave_evento, None)


class AgendaIcloud(Agenda):
    def __init__(self, usuario: str, senha: str, calendario: str = "Entregas OS", sessao=None, base: str = "https://caldav.icloud.com/"):
        if sessao is None:
            import requests
            sessao = requests.Session()
        self.s, self.auth, self.nome, self.base = sessao, (usuario, senha), calendario, base
        self._url: Optional[str] = None

    # --- HTTP com redirecionamento manual (o requests troca PROPFIND por GET em 301/302) ---
    def _req(self, metodo, url, corpo=None, cab=None, ok=(200, 201, 204, 207)):
        for _ in range(5):
            r = self.s.request(metodo, url, data=corpo, headers=cab or {}, auth=self.auth, timeout=25, allow_redirects=False)
            if r.status_code in (301, 302, 307, 308) and r.headers.get("Location"):
                url = urljoin(url, r.headers["Location"])
                continue
            if r.status_code == 401:
                raise PermissionError("iCloud recusou o usuário ou a senha de aplicativo")
            if r.status_code not in ok:
                raise OSError(f"iCloud respondeu {r.status_code} em {metodo}")
            return r, url
        raise OSError("redirecionamentos demais no iCloud")

    def _propfind(self, url, prop_xml, profundidade="0"):
        corpo = f'<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>{prop_xml}</d:prop></d:propfind>'
        r, final = self._req("PROPFIND", url, corpo.encode(), {**XML, "Depth": profundidade}, ok=(207,))
        return ET.fromstring(r.text), final

    def _calendario(self) -> str:
        if self._url:
            return self._url
        raiz, url = self._propfind(self.base, "<d:current-user-principal/>")
        principal = raiz.findtext(f".//{DAV}current-user-principal/{DAV}href")
        if not principal:
            raise OSError("não achei o principal do iCloud")
        raiz, url = self._propfind(urljoin(url, principal), "<c:calendar-home-set/>")
        casa = urljoin(url, raiz.findtext(f".//{CAL}calendar-home-set/{DAV}href"))
        raiz, url = self._propfind(casa, "<d:displayname/><d:resourcetype/>", "1")
        for resp in raiz.findall(f"{DAV}response"):
            nome = resp.findtext(f".//{DAV}displayname")
            if nome == self.nome and resp.find(f".//{DAV}resourcetype/{CAL}calendar") is not None:
                self._url = urljoin(url, resp.findtext(f"{DAV}href"))
                return self._url
        novo = urljoin(casa, f"{uuid.uuid4().hex}/")
        corpo = (f'<?xml version="1.0"?><c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:set><d:prop>'
                 f'<d:displayname>{self.nome}</d:displayname><c:supported-calendar-component-set><c:comp name="VEVENT"/>'
                 f'</c:supported-calendar-component-set></d:prop></d:set></c:mkcalendar>')
        self._req("MKCALENDAR", novo, corpo.encode(), XML, ok=(200, 201))
        self._url = novo
        return novo

    def salvar(self, op):
        dia = date.fromisoformat(op["dia"])
        ics = evento_ics(op["chave"], op["titulo"], dia, op.get("descricao", "").replace("\\n", "\n"), op.get("local", ""))
        self._req("PUT", urljoin(self._calendario(), op["chave"] + ".ics"), ics, {"Content-Type": "text/calendar; charset=utf-8"}, ok=(200, 201, 204))

    def remover(self, chave_evento):
        try:
            self._req("DELETE", urljoin(self._calendario(), chave_evento + ".ics"), ok=(200, 204))
        except OSError as e:
            if "404" not in str(e):
                raise
