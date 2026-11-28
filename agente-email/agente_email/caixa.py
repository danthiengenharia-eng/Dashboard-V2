"""Caixa de entrada: leitura por IMAP (Hostgator) e movimentação para as pastas."""
import base64
import email
import imaplib
import re
from email import policy
from typing import List, Tuple

from .modelos import Mensagem


def utf7_imap(nome: str) -> str:
    """Nome de pasta no formato do IMAP (UTF-7 modificado), ex.: 'Conclusão OS' -> 'Conclus&AOM-o OS'."""
    saida, buf = [], ""

    def esvaziar():
        nonlocal buf
        if buf:
            b64 = base64.b64encode(buf.encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            saida.append("&" + b64 + "-")
            buf = ""

    for ch in nome:
        if 0x20 <= ord(ch) <= 0x7E:
            esvaziar()
            saida.append("&-" if ch == "&" else ch)
        else:
            buf += ch
    esvaziar()
    return "".join(saida)


def _sem_html(html: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", html))


def ler_mensagem(bruto: bytes, uid: str = "") -> Mensagem:
    m = email.message_from_bytes(bruto, policy=policy.default)
    corpo = ""
    parte = m.get_body(preferencelist=("plain", "html"))
    if parte is not None:
        try:
            corpo = parte.get_content()
        except Exception:
            corpo = parte.get_payload(decode=True).decode("latin-1", errors="replace")
        if parte.get_content_type() == "text/html":
            corpo = _sem_html(corpo)
    anexos = []
    for a in m.iter_attachments():
        nome = a.get_filename() or ""
        dados = a.get_payload(decode=True) or b""
        anexos.append((nome, dados))
    return Mensagem(str(m.get("From", "")), str(m.get("Subject", "")), corpo, anexos,
                    id=(str(m.get("Message-ID", "")).strip() or uid), bruto=bruto)


class Caixa:
    def listar(self) -> List[Tuple[str, Mensagem]]:
        raise NotImplementedError

    def mover(self, uid: str, pasta: str) -> None:
        raise NotImplementedError

    def fechar(self) -> None:
        pass


class CaixaMemoria(Caixa):
    def __init__(self, mensagens=None):
        self.mensagens = list(mensagens or [])   # [(uid, Mensagem)]
        self.movidas = {}

    def listar(self):
        return [(u, m) for u, m in self.mensagens if u not in self.movidas]

    def mover(self, uid, pasta):
        self.movidas[uid] = pasta


class CaixaImap(Caixa):
    LIMITE = 50

    def __init__(self, servidor: str, usuario: str, senha: str, porta: int = 993, origem: str = "INBOX"):
        self.c = imaplib.IMAP4_SSL(servidor, porta)
        self.c.login(usuario, senha)
        self.origem = origem
        self.c.select(origem)

    def listar(self):
        tipo, dados = self.c.uid("SEARCH", None, "FROM", '"caixa.gov.br"')
        uids = (dados[0] or b"").split()[-self.LIMITE:]
        saida = []
        for u in uids:
            tipo, partes = self.c.uid("FETCH", u, "(BODY.PEEK[])")
            if tipo != "OK" or not partes or not isinstance(partes[0], tuple):
                continue
            saida.append((u.decode(), ler_mensagem(partes[0][1], u.decode())))
        return saida

    def _garantir(self, pasta: str):
        codigo = f'"{utf7_imap(pasta)}"'
        tipo, _ = self.c.select(codigo, readonly=True)
        if tipo != "OK":
            self.c.create(codigo)
            self.c.subscribe(codigo)
        self.c.select(self.origem)
        return codigo

    def mover(self, uid, pasta):
        destino = self._garantir(pasta)
        tipo, _ = self.c.uid("MOVE", uid, destino)
        if tipo != "OK":
            self.c.uid("COPY", uid, destino)
            self.c.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
            self.c.expunge()

    def fechar(self):
        try:
            self.c.logout()
        except Exception:
            pass
