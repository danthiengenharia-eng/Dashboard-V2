"""Cria a linha de uma nova OS a partir da convocação, com as mesmas regras do dashboard (salvar())."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from .config import Configuracao, mes_abreviado, mes_para_pasta, nome_pasta_os
from .deslocamento import SUFIXO, identificar
from .texto import normalizar


def _brl(v: float) -> str:
    return "R$ " + f"{v:.2f}".replace(".", ",")


def _num(brl: Optional[str]) -> Optional[float]:
    if not brl:
        return None
    try:
        return float(brl.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def achar_atividade(codigo: str, atv: Dict[str, dict]) -> Optional[str]:
    """Mesmo critério do dashboard: exata, prefixo, contém (todas normalizadas)."""
    norm = lambda s: "".join(c for c in (s or "").upper() if c not in " .-")
    alvo = norm(codigo)
    chaves = list(atv)
    return (next((k for k in chaves if norm(k) == alvo), None)
            or next((k for k in chaves if norm(k).startswith(alvo)), None)
            or next((k for k in chaves if alvo in norm(k)), None))


@dataclass
class NovaOS:
    campos: Dict[str, str]
    pasta_mes: str
    pasta_os: str
    avisos: List[str] = field(default_factory=list)


def montar(conv: dict, cfg: Configuracao, itens_existentes: List[str], hoje: date) -> (Optional[NovaOS], List[str]):
    """Devolve (OS, avisos). OS é None quando falta algo obrigatório (o dashboard também exige)."""
    faltando = [r for r, k in (("número da OS", "os"), ("atividade", "atividade"), ("endereço", "endereco"),
                               ("bairro", "bairro"), ("município", "municipio"), ("CEP", "cep"), ("data da OS", "data_os"))
                if not conv.get(k)]
    if faltando:
        return None, ["faltam dados na convocação: " + ", ".join(faltando)]

    avisos: List[str] = []
    atv = achar_atividade(conv["atividade"], cfg.atv)
    if not atv:
        return None, [f"atividade '{conv['atividade']}' não está cadastrada na configuração"]
    a = cfg.atv[atv]

    desloc = identificar(conv["municipio"], {"txt": _num(conv.get("valor_deslocamento"))}, cfg.mun)
    if not desloc.municipio:
        return None, [f"município '{conv['municipio']}' não está cadastrado na configuração"]
    tem_desloc = a.get("d", True)
    vos = float(a.get("v") or 0)
    vd = 0.0
    mun_gravar = desloc.municipio
    if tem_desloc:
        vd = desloc.especial_esperado if desloc.especial else desloc.padrao
        mun_gravar = desloc.municipio_para_gravar if desloc.especial is not None else desloc.municipio
        if desloc.especial is None:
            avisos += ["DESLOCAMENTO A CONFERIR (gravado como padrão): " + x for x in desloc.avisos]

    d, m, y = (int(x) for x in conv["data_os"].split("/"))
    entrada = date(y, m, d)
    entrega = entrada + timedelta(days=int(a["p"])) if a.get("p") else None
    mes = mes_abreviado(hoje)

    item = max([int(i) for i in itens_existentes if str(i).isdigit()] + [0]) + 1
    polo = cfg.mun[desloc.municipio].get("polo", "")
    campos = {
        "item": str(item), "os": conv["os"].replace("/", ""), "aceita": "TRUE", "atv": atv, "tv": "Interna",
        "polo": polo, "mun": mun_gravar, "bairro": conv["bairro"], "tip": conv.get("tipologia") or "",
        "end": conv["endereco"], "area": conv.get("area") or "", "cep": conv["cep"], "mes": mes,
        "siopi": entrada.strftime("%d/%m/%Y"), "pept": "FALSE",
        "ent": entrega.strftime("%d/%m/%Y") if entrega else "",
        "vis": "FALSE", "lau": "FALSE", "vos": _brl(vos), "fich": "FALSE", "vd": _brl(vd), "vt": _brl(vos + vd),
        "st": "Sem vistoria - não agendado", "va": "", "rsm": "", "rev": "FALSE", "abr": "", "prz": "",
        "matricula": conv.get("matricula") or "", "cnm": "", "vcv": "", "categoria": "",
    }
    return NovaOS(campos, mes_para_pasta(mes, cfg.fmt_pasta), nome_pasta_os(item, atv, conv["os"], cfg.fmt_pasta_os), avisos), []
