"""Lê o dashboard-cef-config.json (o mesmo arquivo que o dashboard mantém no Drive).

O arquivo contém chaves de API: este módulo só expõe o que o agente precisa e nunca as imprime.
"""
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

from .planilha import COL_PADRAO

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_EXT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


@dataclass
class Configuracao:
    planilha_id: str
    aba: str
    colunas: Dict[str, int]
    fmt_pasta: str
    fmt_pasta_os: str
    subpastas: List[dict]
    atv: Dict[str, dict]
    mun: Dict[str, dict]
    polos: List[dict] = field(default_factory=list)
    pasta_raiz_id: str = ""
    txt_nome: str = "convocacao.txt"
    txt_destino: str = "root"

    @classmethod
    def de_dict(cls, c: dict) -> "Configuracao":
        return cls(
            planilha_id=c["sid"], aba=c["sht"],
            colunas={**COL_PADRAO, **(c.get("cols") or {})},
            fmt_pasta=c.get("fmtPasta") or "MMMM YYYY", fmt_pasta_os=c.get("fmtPastaOS") or "{nr}-{osb}",
            subpastas=c.get("subp") or [], atv=c.get("atv") or {}, mun=c.get("mun") or {},
            polos=c.get("polos") or [], pasta_raiz_id=c.get("did", ""),
            txt_nome=c.get("txt_name_tpl") or "convocacao.txt", txt_destino=c.get("txt_folder_dest") or "root",
        )

    @classmethod
    def carregar(cls, caminho: str) -> "Configuracao":
        with open(caminho, encoding="utf-8-sig") as f:
            return cls.de_dict(json.load(f))


def mes_abreviado(d: date) -> str:
    """Formato da coluna 'mês de faturamento' (ex.: nov-26)."""
    return f"{MESES[d.month - 1]}-{str(d.year)[2:]}"


def mes_para_pasta(mes: str, fmt: str) -> str:
    """Espelha mes2pasta() do dashboard. `mes` no formato 'nov-26'."""
    mmm, aa = mes.replace(".", "").split("-")
    aa4 = aa if len(aa) == 4 else "20" + aa
    idx = MESES.index(mmm.lower())
    return (fmt.replace("MMMM", MESES_EXT[idx]).replace("MMM", mmm.lower()).replace("YYYY", aa4)
            .replace("MM", str(idx + 1).zfill(2)).replace("YY", aa4[-2:]))


def nome_pasta_os(item, atv: str, os_numero: str, fmt: str) -> str:
    """Espelha nomePasta() do dashboard."""
    osp = os_numero.replace("/", "")
    return (fmt.replace("{nr}", str(item)).replace("{atv}", atv or "")
            .replace("{os}", osp.replace(".", "")).replace("{osb}", osp))
