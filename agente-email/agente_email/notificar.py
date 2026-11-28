"""Avisos no iPhone pelo ntfy (app gratuito) e arquivo de agenda (.ics) para o Calendário."""
import json
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional, Tuple


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def evento_ics(os_numero: str, titulo: str, dia: date, descricao: str = "") -> bytes:
    """Evento de dia inteiro com lembrete na véspera, para o Calendário do iPhone."""
    fim = dia + timedelta(days=1)
    esc = lambda t: t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Danthi//Agente//PT", "BEGIN:VEVENT",
              f"UID:{os_numero.replace('/', '')}@danthi", f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
              f"DTSTART;VALUE=DATE:{dia:%Y%m%d}", f"DTEND;VALUE=DATE:{fim:%Y%m%d}",
              f"SUMMARY:{esc(titulo)}", f"DESCRIPTION:{esc(descricao)}",
              "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", f"DESCRIPTION:{esc(titulo)}", "END:VALARM",
              "END:VEVENT", "END:VCALENDAR"]
    return ("\r\n".join(linhas) + "\r\n").encode("utf-8")


class Notificador:
    def enviar(self, titulo: str, texto: str, prioridade: str = "default", anexo: Optional[Tuple[str, bytes]] = None) -> None:
        raise NotImplementedError


class NotificadorMemoria(Notificador):
    def __init__(self):
        self.enviados: List[dict] = []

    def enviar(self, titulo, texto, prioridade="default", anexo=None):
        self.enviados.append({"titulo": titulo, "texto": texto, "prioridade": prioridade, "anexo": anexo})


class NotificadorNulo(Notificador):
    def enviar(self, *a, **k):
        pass


def _http_padrao(metodo: str, url: str, cabecalhos: dict, corpo: bytes) -> int:
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


class NtfyNotificador(Notificador):
    def __init__(self, servidor: str, topico: str, token: str = "", http: Callable = _http_padrao):
        self.servidor, self.topico, self.token, self.http = servidor.rstrip("/"), topico, token, http

    def _auth(self) -> dict:
        return {"Authorization": "Bearer " + self.token} if self.token else {}

    def enviar(self, titulo, texto, prioridade="default", anexo=None):
        prio = {"low": 2, "default": 3, "high": 4, "urgent": 5}.get(prioridade, 3)
        if anexo:  # anexo = (nome, bytes): no iPhone, tocar no .ics adiciona ao Calendário
            cab = {**self._auth(), "Filename": _ascii(anexo[0]), "Title": _ascii(titulo),
                   "Message": _ascii(texto).replace("\n", " "), "Priority": str(prio)}
            self.http("PUT", f"{self.servidor}/{self.topico}", cab, anexo[1])
        else:
            corpo = json.dumps({"topic": self.topico, "title": titulo, "message": texto, "priority": prio}, ensure_ascii=False)
            self.http("POST", self.servidor, {**self._auth(), "Content-Type": "application/json"}, corpo.encode("utf-8"))
