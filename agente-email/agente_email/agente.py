"""Uma rodada do agente: lê a caixa, aplica as regras, arquiva, move o e-mail e avisa.

Ordem de segurança: planilha -> pastas/arquivos -> mover e-mail. O que já foi feito fica registrado
em `estado`, então uma falha no meio é retomada na rodada seguinte sem duplicar nada.
"""
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Dict, Optional

from .acoes import Resultado, aplicar
from .caixa import Caixa
from .classificador import classificar
from .config import Configuracao
from .criar_os import NovaOS
from .drive import DriveLocal
from .estado import Estado
from .notificar import Notificador, evento_ics
from .planilha import Planilha

log = logging.getLogger("agente")

PASTAS_PADRAO = {"convocacao": "Ordem de Serviço", "conclusao": "Conclusão OS", "cancelamento": "Cancelamento OS",
                 "pept": "Pendências PEPT", "revisao": None}
ROTULO = {"criada": "Nova OS", "concluida": "OS concluída", "cancelada": "OS cancelada",
          "revisao": "Revisão solicitada", "pept_sinalizada": "PEPT resolvida pela CEF"}


@dataclass
class Contexto:
    caixa: Caixa
    plan: Planilha
    drive: DriveLocal
    notif: Notificador
    cfg: Configuracao
    estado: Estado
    regras: dict = field(default_factory=dict)
    pastas: Dict[str, Optional[str]] = field(default_factory=lambda: dict(PASTAS_PADRAO))
    hoje: date = field(default_factory=date.today)


def _avisar(ctx: Contexto, mid: str, chave: str, titulo: str, texto: str, prioridade="high", anexo=None):
    if ctx.estado.primeira_vez(mid, chave):
        ctx.notif.enviar(titulo, texto, prioridade, anexo)


def _notificar_sucesso(ctx: Contexto, tipo: str, os_numero: str, r: Resultado):
    titulo = ROTULO.get(r.acao, r.acao)
    texto, anexo = os_numero, None
    if r.nova_os:
        c = r.nova_os.campos
        titulo = f"Nova OS {c['item']} · {c['mun'].replace(' (Deslocamento especial)', '')}"
        texto = f"{c['atv']} · {c['vt']} · entrega {c['ent']}\n{c['end']}, {c['bairro']}"
        if "Deslocamento especial" in c["mun"]:
            texto += "\nDeslocamento especial"
        if c["ent"]:
            dia = datetime.strptime(c["ent"], "%d/%m/%Y").date()
            anexo = (f"OS{c['item']}.ics", evento_ics(os_numero, f"Entrega OS {c['item']} · {c['atv']}", dia, texto))
    if r.avisos:
        texto += "\n⚠ " + "\n⚠ ".join(r.avisos)
    ctx.notif.enviar(titulo, texto, "high" if r.avisos else "default", anexo)


def processar(ctx: Contexto, uid: str, msg) -> None:
    mid = msg.id or uid
    est = ctx.estado.get(mid)
    if est.get("etapa") == "completo":
        return
    c = classificar(msg)
    if c.tipo == "desconhecido":
        _avisar(ctx, mid, "desconhecido", "E-mail da CEF não reconhecido", f"{msg.assunto}\n({'; '.join(c.avisos)})", "default")
        return

    if est.get("etapa") == "aplicado":      # retomada: a planilha já foi atualizada
        nova = NovaOS(**est["nova"]) if est.get("nova") else None
        r = Resultado(True, est["acao"], avisos=est.get("avisos", []), arquivos=est.get("arquivos", []),
                      nova_os=nova, pode_mover_email=True)
    else:
        r = aplicar(c, msg, ctx.plan, ctx.regras, ctx.hoje, ctx.cfg)
        if not r.aplicado:
            _avisar(ctx, mid, "nao_aplicado", f"Não processei: {c.tipo} {c.os_numero or ''}", "; ".join(r.avisos))
            return
        ctx.estado.set(mid, etapa="aplicado", acao=r.acao, avisos=r.avisos, arquivos=r.arquivos,
                       nova=asdict(r.nova_os) if r.nova_os else None)

    try:
        if r.nova_os:
            ctx.drive.criar_estrutura(r.nova_os, ctx.cfg, msg)
        if "pept_resposta.json" in r.arquivos and not ctx.drive.sinalizar_pept(c.os_numero, msg.assunto):
            r.avisos.append("pasta da OS não encontrada para gravar a sinalização da PEPT")
        pasta = ctx.pastas.get(c.tipo)
        if pasta and r.pode_mover_email:
            ctx.caixa.mover(uid, pasta)
    except Exception as e:   # será retomado na próxima rodada
        log.exception("falha ao concluir %s", mid)
        _avisar(ctx, mid, "erro", f"Erro ao concluir {c.tipo} {c.os_numero}", f"{type(e).__name__}: {e}")
        return

    ctx.estado.set(mid, etapa="completo")
    _notificar_sucesso(ctx, c.tipo, c.os_numero, r)


def rodar_uma_vez(ctx: Contexto) -> int:
    n = 0
    for uid, msg in ctx.caixa.listar():
        try:
            processar(ctx, uid, msg)
            n += 1
        except Exception:
            log.exception("erro inesperado no e-mail %s", uid)
    return n
