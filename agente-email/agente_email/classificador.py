"""Reconhece o tipo do e-mail da CEF e extrai o número da OS.

Regra de segurança: qualquer dúvida (tipo não reconhecido, OS ausente ou
divergente entre assunto e corpo) gera aviso e o agente NÃO age sozinho.
"""
import re

from .modelos import Classificacao, Mensagem
from .texto import normalizar

RE_OS = re.compile(r"\d{4}\.\d{4}\.\d{9}/\d{4}\.\d{2}\.\d{2}")

# Ordem importa só para legibilidade; os padrões não se sobrepõem.
PADROES_ASSUNTO = [
    ("convocacao", re.compile(r"convoca\S{0,3}o de ordem d[ao] servi\S{0,2}o")),
    ("conclusao", re.compile(r"conclus\S{0,3}o d[ao] ordem (de )?servi\S{0,2}o")),
    ("cancelamento", re.compile(r"cancelamento d[ao] ordem (de )?servi\S{0,2}o")),
    ("revisao", re.compile(r"solicita\S{0,3}o de revis\S{0,3}o do valor de avalia\S{0,3}o")),
    ("pept", re.compile(r"resolu\S{0,3}o do pept")),
]

# Nestes tipos o número da OS vem no corpo, não no assunto.
OS_NO_CORPO = {
    "revisao": re.compile(r"\bOS\s+(" + RE_OS.pattern + ")"),
    "pept": re.compile(r"\bOS\s+(" + RE_OS.pattern + ")"),
}


def remetente_caixa(remetente: str) -> bool:
    return bool(re.search(r"@caixa\.gov\.br\s*>?\s*$", (remetente or "").strip(), re.I))


def classificar(msg: Mensagem) -> Classificacao:
    avisos = []
    if not remetente_caixa(msg.remetente):
        return Classificacao("desconhecido", None, ["remetente fora de @caixa.gov.br"])

    assunto = normalizar(msg.assunto)
    tipos = [t for t, p in PADROES_ASSUNTO if p.search(assunto)]
    if len(tipos) != 1:
        return Classificacao("desconhecido", None, ["assunto não reconhecido" if not tipos else "assunto ambíguo"])
    tipo = tipos[0]

    os_assunto = RE_OS.search(msg.assunto or "")
    os_corpo = None
    if tipo in OS_NO_CORPO:
        m = OS_NO_CORPO[tipo].search(msg.corpo or "")
        os_corpo = m.group(1) if m else None
    else:
        m = RE_OS.search(msg.corpo or "")
        os_corpo = m.group(0) if m else None

    numero = os_assunto.group(0) if os_assunto else os_corpo
    if not numero:
        avisos.append("número da OS não encontrado")
    elif os_assunto and os_corpo and os_assunto.group(0) != os_corpo and tipo not in OS_NO_CORPO:
        avisos.append("número da OS diverge entre assunto e corpo")
    return Classificacao(tipo, numero, avisos)
