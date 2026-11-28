"""Utilidades de texto."""
import re
import unicodedata

def _byte(ch: str):
    """Byte original do caractere lido como cp1252/latin-1 (None se impossível)."""
    for codec in ("cp1252", "latin-1"):
        try:
            return ch.encode(codec)[0]
        except (UnicodeEncodeError, IndexError):
            continue
    return None


def _continuacao(ch: str) -> bool:
    b = _byte(ch)
    return b is not None and 0x80 <= b <= 0xBF


def _reparar_linha(linha: str) -> str:
    if "Ã" not in linha and "Â" not in linha:
        return linha
    # Todo 'Ã'/'Â' precisa vir seguido de byte de continuação; senão é texto legítimo ('SÃO').
    for i, ch in enumerate(linha):
        if ch in "ÃÂ" and not (i + 1 < len(linha) and _continuacao(linha[i + 1])):
            return linha
    dados = bytearray()
    for ch in linha:
        b = _byte(ch)
        if b is None:
            return linha
        dados.append(b)
    return dados.decode("utf-8", errors="replace")


def reparar_mojibake(s: str) -> str:
    """Corrige UTF-8 lido como latin-1/cp1252 (ex.: 'ConvocaÃ§Ã£o' -> 'Convocação')."""
    if not s:
        return s
    return "\n".join(_reparar_linha(l) for l in s.split("\n"))


def normalizar(texto: str) -> str:
    texto = reparar_mojibake(texto or "")
    sem = unicodedata.normalize("NFKD", texto)
    sem = "".join(c for c in sem if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem).strip().lower()
