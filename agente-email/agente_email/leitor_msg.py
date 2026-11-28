"""Lê arquivos .msg do Outlook (apenas para testes locais com exemplos reais).

Em produção o agente lê pelo IMAP; este módulo serve para validar o
reconhecimento com e-mails salvos.
"""
import olefile

from .modelos import Mensagem
from .texto import reparar_mojibake


def _txt(ole, nome):
    if not ole.exists(nome):
        return ""
    return ole.openstream(nome).read().decode("utf-16-le", errors="replace").rstrip("\x00")


def ler_msg(caminho: str) -> Mensagem:
    ole = olefile.OleFileIO(caminho)
    corpo = _txt(ole, "__substg1.0_1000001F")
    remetente = _txt(ole, "__substg1.0_0C1F001F") or _txt(ole, "__substg1.0_5D01001F")
    anexos = []
    for partes in ole.listdir():
        if partes[0].startswith("__attach") and partes[-1] == "__substg1.0_37010102":
            base = "/".join(partes[:-1])
            nome = _txt(ole, base + "/__substg1.0_3707001F") or _txt(ole, base + "/__substg1.0_3704001F")
            anexos.append((reparar_mojibake(nome), ole.openstream("/".join(partes)).read()))
    return Mensagem(remetente, reparar_mojibake(_txt(ole, "__substg1.0_0037001F")), corpo, anexos)
