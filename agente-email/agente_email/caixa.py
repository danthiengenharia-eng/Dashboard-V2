"""Caixa de entrada: leitura por IMAP (Hostgator) e movimentação para as pastas."""
import base64
import email
import imaplib
import re
from datetime import date, datetime
from email import policy
from email.utils import parsedate_to_datetime
from typing import List, Optional, Tuple

from .modelos import Mensagem
from .texto import normalizar


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
    try:
        quando = parsedate_to_datetime(str(m.get("Date", "")))
    except (TypeError, ValueError):
        quando = None
    return Mensagem(str(m.get("From", "")), str(m.get("Subject", "")), corpo, anexos,
                    id=(str(m.get("Message-ID", "")).strip() or uid), bruto=bruto, data=quando)


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


def separar_list(linha: bytes) -> Tuple[str, str]:
    """(separador, nome decodificado) de uma linha do comando LIST."""
    m = re.match(rb'\(.*?\)\s+(?:"(.*?)"|NIL)\s+(.*)$', linha.strip())
    if not m:
        return "", utf7_texto(linha.decode("ascii", "ignore").strip().strip('"'))
    delim = (m.group(1) or b"").decode()
    nome = m.group(2).strip()
    if nome.startswith(b'"') and nome.endswith(b'"'):
        nome = nome[1:-1]
    return delim, utf7_texto(nome.decode("ascii", "ignore"))


def resolver_pasta(existentes: List[str], delim: str, desejada: str) -> str:
    """Usa a pasta que já existe (mesmo dentro de INBOX., sem diferenciar acento/maiúscula) ou o nome para criar."""
    if desejada in existentes:
        return desejada
    alvo = normalizar(desejada)
    for n in existentes:
        ultimo = n.split(delim)[-1] if delim else n
        if normalizar(ultimo) == alvo:
            return n
    prefixo = "INBOX" + delim if delim and any(n.startswith("INBOX" + delim) for n in existentes) else ""
    return prefixo + desejada


class CaixaImap(Caixa):
    LIMITE = 200

    def __init__(self, servidor: str, usuario: str, senha: str, porta: int = 993, origem: str = "INBOX", desde: Optional[date] = None):
        self.c = imaplib.IMAP4_SSL(servidor, porta)
        self.c.login(usuario, senha)
        self.origem, self.desde = origem, desde
        self.c.select(origem)
        self._delim, self._nomes = "", []

    def _carregar_pastas(self):
        tipo, pastas = self.c.list()
        pares = [separar_list(p) for p in (pastas or []) if p]
        self._delim = next((d for d, _ in pares if d), "")
        self._nomes = [n for _, n in pares]

    def listar(self):
        criterios = ["FROM", '"caixa.gov.br"']
        if self.desde:
            criterios += ["SINCE", self.desde.strftime("%d-%b-%Y")]
        tipo, dados = self.c.uid("SEARCH", None, *criterios)
        uids = (dados[0] or b"").split()[:self.LIMITE]      # do mais antigo ao mais novo: a numeração segue a ordem de chegada
        saida = []
        for u in uids:
            tipo, partes = self.c.uid("FETCH", u, "(BODY.PEEK[])")
            if tipo != "OK" or not partes or not isinstance(partes[0], tuple):
                continue
            m = ler_mensagem(partes[0][1], u.decode())
            if self.desde and m.data and m.data.date() < self.desde:
                continue                      # a busca é por dia; aqui o filtro exato
            saida.append((u.decode(), m))
        return saida

    def _garantir(self, pasta: str) -> str:
        if not self._nomes:
            self._carregar_pastas()
        nome = resolver_pasta(self._nomes, self._delim, pasta)
        codigo = f'"{utf7_imap(nome)}"'
        if nome not in self._nomes:
            self.c.create(codigo)
            self.c.subscribe(codigo)
            self._nomes.append(nome)
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


def candidatos_servidor(usuario: str, informado: str = "") -> list:
    """Servidores IMAP prováveis para o e-mail (o informado vem primeiro)."""
    dominio = usuario.split("@", 1)[1] if "@" in usuario else ""
    lista = [informado] if informado else []
    if dominio:
        lista += [f"mail.{dominio}", f"imap.{dominio}", dominio]
    return list(dict.fromkeys(x for x in lista if x))


def utf7_texto(bruto: str) -> str:
    """Desfaz o UTF-7 modificado do IMAP: 'Conclus&AOM-o' -> 'Conclusão'."""
    def volta(t):
        b64 = t.group(1)
        if not b64:
            return "&"
        b64 = b64.replace(",", "/")
        return base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-be")
    return re.sub(r"&([^-]*)-", volta, bruto)


def decodificar_pasta(linha: bytes) -> str:
    """Nome da pasta no fim de uma linha de LIST, em texto normal."""
    return separar_list(linha)[1]


def separar_list(linha: bytes) -> Tuple[str, str]:
    """(separador, nome decodificado) de uma linha do comando LIST."""
    m = re.match(rb'\(.*?\)\s+(?:"(.*?)"|NIL)\s+(.*)$', linha.strip())
    if not m:
        return "", utf7_texto(linha.decode("ascii", "ignore").strip().strip('"'))
    delim = (m.group(1) or b"").decode()
    nome = m.group(2).strip()
    if nome.startswith(b'"') and nome.endswith(b'"'):
        nome = nome[1:-1]
    return delim, utf7_texto(nome.decode("ascii", "ignore"))


def resolver_pasta(existentes: List[str], delim: str, desejada: str) -> str:
    """Usa a pasta que já existe (mesmo dentro de INBOX., sem diferenciar acento/maiúscula) ou o nome para criar."""
    if desejada in existentes:
        return desejada
    alvo = normalizar(desejada)
    for n in existentes:
        ultimo = n.split(delim)[-1] if delim else n
        if normalizar(ultimo) == alvo:
            return n
    prefixo = "INBOX" + delim if delim and any(n.startswith("INBOX" + delim) for n in existentes) else ""
    return prefixo + desejada


class CaixaImap(Caixa):
    LIMITE = 200

    def __init__(self, servidor: str, usuario: str, senha: str, porta: int = 993, origem: str = "INBOX", desde: Optional[date] = None):
        self.c = imaplib.IMAP4_SSL(servidor, porta)
        self.c.login(usuario, senha)
        self.origem, self.desde = origem, desde
        self.c.select(origem)
        self._delim, self._nomes = "", []

    def _carregar_pastas(self):
        tipo, pastas = self.c.list()
        pares = [separar_list(p) for p in (pastas or []) if p]
        self._delim = next((d for d, _ in pares if d), "")
        self._nomes = [n for _, n in pares]

    def listar(self):
        criterios = ["FROM", '"caixa.gov.br"']
        if self.desde:
            criterios += ["SINCE", self.desde.strftime("%d-%b-%Y")]
        tipo, dados = self.c.uid("SEARCH", None, *criterios)
        uids = (dados[0] or b"").split()[:self.LIMITE]      # do mais antigo ao mais novo: a numeração segue a ordem de chegada
        saida = []
        for u in uids:
            tipo, partes = self.c.uid("FETCH", u, "(BODY.PEEK[])")
            if tipo != "OK" or not partes or not isinstance(partes[0], tuple):
                continue
            m = ler_mensagem(partes[0][1], u.decode())
            if self.desde and m.data and m.data.date() < self.desde:
                continue                      # a busca é por dia; aqui o filtro exato
            saida.append((u.decode(), m))
        return saida

    def _garantir(self, pasta: str) -> str:
        if not self._nomes:
            self._carregar_pastas()
        nome = resolver_pasta(self._nomes, self._delim, pasta)
        codigo = f'"{utf7_imap(nome)}"'
        if nome not in self._nomes:
            self.c.create(codigo)
            self.c.subscribe(codigo)
            self._nomes.append(nome)
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


def candidatos_servidor(usuario: str, informado: str = "") -> list:
    """Servidores IMAP prováveis para o e-mail (o informado vem primeiro)."""
    dominio = usuario.split("@", 1)[1] if "@" in usuario else ""
    lista = [informado] if informado else []
    if dominio:
        lista += [f"mail.{dominio}", f"imap.{dominio}", dominio]
    return list(dict.fromkeys(x for x in lista if x))


def decodificar_pasta(linha: bytes) -> str:
    """Nome da pasta como veio do LIST (UTF-7 modificado) em texto normal."""
    m = re.search(rb'"([^"]*)"\s*$|\s(\S+)\s*$', linha)
    bruto = (m.group(1) or m.group(2) or b"").decode("ascii", "ignore") if m else ""

    def volta(t):
        b64 = t.group(1)
        if not b64:
            return "&"
        b64 = b64.replace(",", "/")
        return base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-be")
    return re.sub(r"&([^-]*)-", volta, bruto)


def testar_conexao(usuario: str, senha: str, servidor: str = "", porta: int = 993, esperadas=()) -> list:
    """Tenta entrar em cada servidor candidato. Devolve linhas de texto com o resultado (nunca mostra a senha)."""
    saida = []
    for srv in candidatos_servidor(usuario, servidor):
        try:
            c = imaplib.IMAP4_SSL(srv, porta, timeout=20)
        except Exception as e:
            saida.append(f"✗ {srv}: não conectou ({type(e).__name__})")
            continue
        try:
            c.login(usuario, senha)
        except imaplib.IMAP4.error:
            saida.append(f"~ {srv}: servidor responde, mas usuário ou senha recusados")
            continue
        saida.append(f"✓ {srv}: ENTROU. Use IMAP_SERVIDOR={srv}")
        tipo, pastas = c.list()
        pares = [separar_list(p) for p in (pastas or []) if p]
        delim = next((d for d, _ in pares if d), "")
        nomes = [n for _, n in pares]
        saida.append("   pastas do servidor: " + ", ".join(nomes))
        for esp in esperadas:
            r = resolver_pasta(nomes, delim, esp)
            saida.append(f"   '{esp}': " + (f"existe como '{r}'" if r in nomes else f"será criada como '{r}'"))
        tipo, n = c.select("INBOX", readonly=True)
        saida.append(f"   caixa de entrada: {(n[0] or b'0').decode()} e-mail(s)")
        c.logout()
        break
    return saida


def ordenar_cronologicamente(mensagens):
    """Do e-mail emitido primeiro ao último (cabeçalho Date). Sem data, mantém a ordem de chegada."""
    def chave(par):
        d = par[1].data
        try:
            return d.timestamp() if d else 0.0
        except (OverflowError, OSError, ValueError):
            return 0.0
    return sorted(mensagens, key=chave)
