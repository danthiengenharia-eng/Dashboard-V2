"""Tipologia a partir dos textos da convocação, quando não há campo "Tipologia" (ex.: acompanhamento de obra)."""
import re
from typing import List, Optional, Tuple

from .texto import normalizar

OBRA = re.compile(r"^E-?401")
PADRAO_OBRA = "Obra Residencial"


def e_acompanhamento_de_obra(atividade: str) -> bool:
    return bool(OBRA.match((atividade or "").upper().replace(" ", "")))


def inferir(textos: str, atividade: str, opcoes: List[str]) -> Tuple[Optional[str], str]:
    """(tipologia, aviso). Procura o nome de uma opção no texto; em acompanhamento de obra assume Obra Residencial."""
    n = normalizar(textos or "")
    por_tamanho = sorted(opcoes, key=lambda o: len(normalizar(o)), reverse=True)
    achada = next((o for o in por_tamanho if normalizar(o) and normalizar(o) in n), None)
    if e_acompanhamento_de_obra(atividade):
        if achada and normalizar(achada) == normalizar(PADRAO_OBRA):
            return achada, ""
        if "residencial" in n:
            return next((o for o in opcoes if normalizar(o) == normalizar(PADRAO_OBRA)), PADRAO_OBRA), ""
        return PADRAO_OBRA, "tipologia assumida como Obra Residencial (acompanhamento de obra): conferir"
    return achada, ""
