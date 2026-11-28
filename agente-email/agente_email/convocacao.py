"""Interpreta o .txt de convocação da CEF.

Espelha as regras de parseTxtOS() do dashboard (index.html) para que a OS
criada pelo agente seja idêntica à criada manualmente.
"""
import re
from typing import Dict, Optional

from .texto import reparar_mojibake

MINUSCULAS = {"da", "de", "di", "do", "du", "das", "dos", "e"}
PREFIXOS_LOGRADOURO = ("rua ", "avenida ", "av ", "estrada ", "rodovia ", "travessa ")


def decodificar(dados: bytes) -> str:
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        return dados.decode("cp1252", errors="replace")


def title_case(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    saida = []
    for i, w in enumerate(re.split(r"[ \t]+", s.lower())):
        if not w:
            saida.append("")
        elif w in MINUSCULAS and i != 0:
            saida.append(w)
        else:
            saida.append(w[0].upper() + w[1:])
    return " ".join(saida)


def _get(txt: str, *padroes: str) -> Optional[str]:
    for p in padroes:
        m = re.search(p, txt, re.I)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def _valor(txt: str, rotulo: str) -> Optional[str]:
    return _get(txt, rotulo + r"\.*:\s*R\$\s*([\d.]+,\d{2})")


def interpretar(txt: str) -> Dict[str, Optional[str]]:
    txt = reparar_mojibake(txt)
    os_num = _get(
        txt,
        r"(?:n[úu]mero|OS|ordem|n.mero)[^\n]*?:\s*([0-9]+\.[0-9]+\.[0-9]+/[0-9.]+)",
        r"([0-9]{4}\.[0-9]{4}\.[0-9]{9,}/[0-9.]+)",
    )
    end = _get(txt, r"endere.o[^\n]*?:\s*(.+)")
    bairro = _get(txt, r"bairro[^\n]*?:\s*(.+)")
    if end and " - " in end and not bairro:
        partes = end.split(" - ")
        bairro = partes.pop().strip()
        end = " - ".join(partes).strip()
    if end and not end.lower().startswith(PREFIXOS_LOGRADOURO):
        end = "Rua " + end  # mesma heurística do dashboard

    mun_raw = _get(txt, r"munic.pio[^\n]*?:\s*(.+)", r"cidade[^\n]*?:\s*(.+)")
    uf = None
    if mun_raw:
        m = re.search(r"\s*[/-]\s*([A-Z]{2})\s*$", mun_raw)
        if m:
            uf = m.group(1)
            mun_raw = mun_raw[: m.start()].strip()

    atv_raw = _get(
        txt,
        r"atividade[^\n]*?:\s*([A-Za-z0-9._\-]+)",
        r"c.digo[\s]*(?:da\s*)?atividade[^\n]*?:\s*([A-Za-z0-9._\-]+)",
        r"atv[^\n]*?:\s*([A-Za-z0-9._\-]+)",
    )
    data = _get(
        txt,
        r"ordem de servi.o[^:\n]*:\s*(\d{2}/\d{2}/\d{4})",
        r"data\s*(?:de\s*)?abertura[^:\n]*:\s*(\d{2}/\d{2}/\d{4})",
        r"data\s*(?:de\s*)?atribui.[aã]o[^:\n]*:\s*(\d{2}/\d{2}/\d{4})",
    )
    return {
        "os": os_num,
        "endereco": title_case(end),
        "bairro": title_case(bairro),
        "municipio": title_case(mun_raw),
        "uf": uf,
        "cep": _get(txt, r"cep[^\n]*?:\s*(\d{5}-?\d{3})"),
        "atividade": re.sub(r"[\s.\-]", "", atv_raw.upper()) if atv_raw else None,
        "data_os": data,
        "tipologia": title_case(_get(txt, r"(?:tipologia|tipo de im.vel|tipo do im.vel)[^\n]*?:\s*(.+)")),
        "area": _get(txt, r".rea[^\n]*?:\s*([\d,.]+\s*m[²2]?)"),
        # extras úteis para conferência (o dashboard calcula valores pelas tabelas)
        "prazo_dias": _get(txt, r"prazo de execu..o\.*:\s*(\d+)\s*dia"),
        "valor_servico": _valor(txt, r"valor previsto do servi.o"),
        "valor_deslocamento": _valor(txt, r"valor previsto do deslocamento"),
        "contato_nome": _get(txt, r"nome do contato\.*:\s*(.+)"),
        "contato_telefone": _get(txt, r"telefone contato\.*:\s*(.+)"),
        "matricula": _get(txt, r"matr.cula rgi:\s*(\d+)"),
        "demandante": _get(txt, r"demandante\.*:\s*(.+)"),
        # textos livres onde a CEF costuma dizer o tipo (ex.: acompanhamento de obra residencial)
        "textos_tipo": " | ".join(x for x in (_get(txt, r"assunto\s*\.*:\s*(.+)"), _get(txt, r"descri..o\s*\.*:\s*(.+)"),
                                              _get(txt, r"observa..o\s*\.*:\s*(.+)")) if x),
    }
