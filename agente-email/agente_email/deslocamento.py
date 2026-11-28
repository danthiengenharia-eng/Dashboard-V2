"""Identifica se a OS tem deslocamento especial comparando o valor do e-mail/SIOPI com a configuração.

Regra do dashboard (index.html): deslocamento especial = 21% do valor padrão do município,
arredondado a centavos (Math.round(v*0.21*100)/100). O dashboard grava a marca no próprio
município: "Rio De Janeiro (Deslocamento especial)".
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from .texto import normalizar

FATOR_ESPECIAL = Decimal("0.21")
SUFIXO = " (Deslocamento especial)"
TOLERANCIA = Decimal("0.005")


@dataclass
class Deslocamento:
    especial: Optional[bool]          # True = Sim, False = Não, None = não foi possível decidir
    padrao: Optional[float] = None    # valor padrão do município na configuração
    especial_esperado: Optional[float] = None
    municipio: Optional[str] = None   # nome canônico (como na configuração)
    avisos: List[str] = field(default_factory=list)

    @property
    def campo(self) -> str:
        return {True: "Sim", False: "Não"}.get(self.especial, "Indefinido")

    @property
    def municipio_para_gravar(self) -> Optional[str]:
        """Mesmo formato que o dashboard grava na coluna do município."""
        if not self.municipio:
            return None
        return self.municipio + (SUFIXO if self.especial else "")


def valor_especial(padrao: float) -> float:
    d = (Decimal(str(padrao)) * FATOR_ESPECIAL).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


def achar_municipio(nome: str, municipios: Dict[str, dict]) -> Optional[str]:
    alvo = normalizar((nome or "").replace(SUFIXO, ""))
    for chave in municipios:
        if normalizar(chave) == alvo:
            return chave
    return None


def _igual(a: float, b: float) -> bool:
    return abs(Decimal(str(a)) - Decimal(str(b))) <= TOLERANCIA


def identificar(municipio: str, valores: Dict[str, Optional[float]], municipios: Dict[str, dict]) -> Deslocamento:
    """`valores` = {fonte: valor de deslocamento}, ex.: {"txt": 8.4, "siopi": 8.4}."""
    chave = achar_municipio(municipio, municipios)
    if not chave:
        return Deslocamento(None, avisos=[f"município '{municipio}' não está na configuração"])
    padrao = float(municipios[chave].get("v") or 0)
    esp = valor_especial(padrao)
    r = Deslocamento(None, padrao, esp, chave)

    decisoes = {}
    for fonte, v in valores.items():
        if v is None:
            continue
        if _igual(v, padrao):
            decisoes[fonte] = False
        elif _igual(v, esp):
            decisoes[fonte] = True
        else:
            r.avisos.append(f"{fonte}: deslocamento R$ {v:.2f} não é o padrão (R$ {padrao:.2f}) nem o especial (R$ {esp:.2f})")
    if not valores or all(v is None for v in valores.values()):
        r.avisos.append("nenhuma fonte trouxe o valor do deslocamento")
    if len(set(decisoes.values())) > 1:
        r.avisos.append("as fontes divergem: " + ", ".join(f"{f}={'especial' if d else 'padrão'}" for f, d in decisoes.items()))
        return r
    if r.avisos and not decisoes:
        return r
    if decisoes:
        r.especial = next(iter(decisoes.values()))
    return r
