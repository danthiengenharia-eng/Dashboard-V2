"""Dados dos e-mails de conclusão (valores efetivos para conferência)."""
import re
from typing import Dict, Optional

from .texto import reparar_mojibake


def _g(txt: str, padrao: str) -> Optional[str]:
    m = re.search(padrao, txt, re.I)
    return m.group(1).strip() if m else None


def interpretar_conclusao(corpo: str) -> Dict[str, Optional[str]]:
    corpo = reparar_mojibake(corpo)
    return {
        "data_conclusao": _g(corpo, r"data de conclus.o\s*:\s*(\d{2}/\d{2}/\d{4})"),
        "valor_servico": _g(corpo, r"valor efetivo do servi.o\.*\s*:\s*R\$\s*([\d.]+,\d{2})"),
        "valor_deslocamento": _g(corpo, r"valor efetivo do deslocamento\s*:\s*R\$\s*([\d.]+,\d{2})"),
    }
