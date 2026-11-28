"""Regras de cada tipo de e-mail sobre uma OS já existente.

Espelham o que o dashboard faz ao mudar o status (updSt). Em dúvida, não altera e devolve aviso.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from .config import Configuracao
from .convocacao import decodificar, interpretar
from .criar_os import NovaOS, montar
from .eventos import interpretar_conclusao
from .modelos import Classificacao, Mensagem
from .planilha import Planilha

ZERO = "R$ 0,00"


def _verdadeiro(v) -> bool:
    return str(v).strip().upper() in ("TRUE", "VERDADEIRO", "SIM", "1")


def _data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _num(brl: Optional[str]) -> Optional[float]:
    if not brl:
        return None
    s = brl.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return round(float(s), 2)
    except ValueError:
        return None


@dataclass
class Resultado:
    aplicado: bool
    acao: str
    campos: Dict[str, str] = field(default_factory=dict)
    avisos: List[str] = field(default_factory=list)       # exigem atenção do usuário
    arquivos: List[str] = field(default_factory=list)      # arquivos a gravar na pasta da OS (feito na camada do Drive)
    pode_mover_email: bool = False
    nova_os: Optional[NovaOS] = None                       # OS a criar (pastas e anexos são feitos na camada do Drive)


def _linha_unica(plan: Planilha, os_numero: str):
    achadas = plan.achar_os(os_numero)
    if not achadas:
        return None, "OS não encontrada na planilha"
    if len(achadas) > 1:
        return None, "OS aparece mais de uma vez na planilha"
    return achadas[0], None


def aplicar(c: Classificacao, msg: Mensagem, plan: Planilha, regras: dict, hoje: date, cfg: Optional[Configuracao] = None) -> Resultado:
    if not c.confiavel:
        return Resultado(False, "ignorado", avisos=c.avisos or ["e-mail não confiável"])
    if c.tipo == "convocacao":
        return _criar_os(c, msg, plan, hoje, cfg)

    linha, erro = _linha_unica(plan, c.os_numero)
    if erro:
        return Resultado(False, c.tipo, avisos=[erro])
    ri = linha["ri"]
    avisos: List[str] = []

    if c.tipo == "conclusao":
        campos = {"st": "OS Concluída", "rsm": "", "rev": "FALSE"}
        v = interpretar_conclusao(msg.corpo)
        for chave, rotulo in (("vos", "serviço"), ("vd", "deslocamento")):
            email = _num(v["valor_servico" if chave == "vos" else "valor_deslocamento"])
            plan_v = _num(linha.get(chave))
            if email is not None and plan_v is not None and abs(email - plan_v) > 0.005:
                avisos.append(f"valor de {rotulo} diverge: e-mail R$ {email:.2f} x planilha R$ {plan_v:.2f}")
        plan.atualizar(ri, campos)
        return Resultado(True, "concluida", campos, avisos, pode_mover_email=True)

    if c.tipo == "cancelamento":
        if _verdadeiro(linha.get("vis")) or _verdadeiro(linha.get("lau")) or _verdadeiro(linha.get("fich")):
            avisos.append("OS cancelada JÁ TINHA serviço executado (vistoria, ficha ou laudo): conferir faturamento")
        campos = {"st": "OS Cancelada", "vos": ZERO, "vd": ZERO, "vt": ZERO, "rsm": "", "rev": "FALSE"}
        plan.atualizar(ri, campos)
        return Resultado(True, "cancelada", campos, avisos, pode_mover_email=True)

    if c.tipo == "revisao":
        cfg = regras.get("revisao", {})
        prazo = _data(hoje + timedelta(days=int(cfg.get("prazo_dias_corridos", 6))))
        campos = {"st": cfg.get("status_planilha", "OS em Revisão"), "rev": "TRUE", "abr": _data(hoje), "prz": prazo}
        if linha.get("st") in ("OS Concluída", "OS Cancelada"):
            avisos.append(f"OS estava '{linha.get('st')}' e voltou para revisão")
        plan.atualizar(ri, campos)
        return Resultado(True, "revisao", campos, avisos, pode_mover_email=True)

    if c.tipo == "pept":
        # Não muda status nem prazo: o dashboard controla a suspensão de prazo. Só sinaliza.
        arquivo = "pept_resposta.json"
        avisos.append("PEPT resolvida pela CEF: conferir se atende às exigências")
        return Resultado(True, "pept_sinalizada", {}, avisos, [arquivo], pode_mover_email=True)

    return Resultado(False, c.tipo, avisos=["tipo sem regra"])


def _criar_os(c: Classificacao, msg: Mensagem, plan: Planilha, hoje: date, cfg: Optional[Configuracao]) -> Resultado:
    if cfg is None:
        return Resultado(False, "convocacao", avisos=["configuração do dashboard não carregada"])
    if plan.achar_os(c.os_numero):
        return Resultado(False, "convocacao", avisos=["OS já existe na planilha: nada foi criado"])
    txt = next((decodificar(d) for n, d in msg.anexos if n.lower().endswith(".txt")), msg.corpo)
    conv = interpretar(txt)
    if conv.get("os") and conv["os"].replace("/", "") != c.os_numero.replace("/", ""):
        return Resultado(False, "convocacao", avisos=["OS do anexo diverge da OS do assunto"])
    conv["os"] = conv.get("os") or c.os_numero
    nova, avisos = montar(conv, cfg, [l.get("item", "") for l in plan.listar()], hoje)
    if nova is None:
        return Resultado(False, "convocacao", avisos=avisos)
    nova.campos["item"] = nova.campos["item"]
    plan.adicionar(nova.campos)
    return Resultado(True, "criada", nova.campos, nova.avisos, nova_os=nova, pode_mover_email=True)
