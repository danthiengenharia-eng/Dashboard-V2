"""Uma rodada do agente: lê a caixa, aplica as regras, arquiva, move o e-mail e avisa.

Ordem de segurança: planilha -> pastas/arquivos -> mover e-mail. O que já foi feito fica registrado
em `estado`, então uma falha no meio é retomada na rodada seguinte sem duplicar nada.
"""
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Callable, Dict, Optional

from .agenda import Agenda, ops_nova_os
from .acoes import Resultado, aplicar, preparar_os
from .caixa import Caixa, ordenar_cronologicamente
from .classificador import classificar
from .config import Configuracao
from .criar_os import NovaOS
from .drive import DriveLocal
from .estado import Estado
from .notificar import Notificador, NotificadorColetor, evento_ics
from .planilha import Planilha
from .siopi import SiopiArquivos, campos_planilha, documentos

log = logging.getLogger("agente")

PASTAS_PADRAO = {"convocacao": "Ordem de Serviço", "conclusao": "Conclusão OS", "cancelamento": "Cancelamento OS",
                 "pept": "Pendências PEPT", "revisao": "Revisão OS"}
ROTULO = {"reiteracao": "Reiteração da CEF", "criada": "Nova OS", "concluida": "OS concluída", "cancelada": "OS cancelada",
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
    siopi: Optional[SiopiArquivos] = None        # None = não pede dados ao SIOPI
    agora: Callable = datetime.now
    espera_resposta_s: int = 180                 # o agente do SIOPI precisa pegar o pedido em até 3 min
    espera_total_s: int = 900                    # e terminar a busca em até 15 min
    tentativas_max: int = 3
    permitir_sem_siopi: bool = True               # depois das tentativas, cria a OS sem SIOPI (e avisa) em vez de perder a demanda
    agenda: Optional[Agenda] = None               # compromissos no iCloud; None = só aviso com arquivo .ics
    siopi_fora: bool = False                      # agente do SIOPI offline nesta rodada: não espera de novo


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
        if r.resumo:
            texto += "\nSIOPI: " + r.resumo
        if c["ent"] and ctx.agenda is None:
            dia = datetime.strptime(c["ent"], "%d/%m/%Y").date()
            anexo = (f"OS{c['item']}.ics", evento_ics(os_numero, f"Entrega OS {c['item']} · {c['atv']}", dia, texto))
    if r.agenda and ctx.agenda is not None:
        texto += "\n📅 agenda atualizada" if any(o["acao"] == "salvar" for o in r.agenda) else "\n📅 removida da agenda"
    if r.avisos:
        texto += "\n⚠ " + "\n⚠ ".join(r.avisos)
    ctx.notif.enviar(titulo, texto, "high" if r.avisos else "default", anexo)



def _enfileirar_agenda(ctx: Contexto, ops) -> None:
    if ctx.agenda is None:
        return
    for op in ops or []:                       # a última operação de cada compromisso vale
        ctx.estado.set("agenda:" + op["chave"], etapa="pendente", tentativas=0, op=op)


def sincronizar_agenda(ctx: Contexto) -> None:
    """Executa as operações pendentes; se o iCloud falhar, tenta de novo na próxima rodada (e avisa uma vez)."""
    if ctx.agenda is None:
        return
    for chave, est in ctx.estado.itens("agenda:"):
        if est.get("etapa") != "pendente":
            continue
        try:
            ctx.agenda.executar(est["op"])
            ctx.estado.set(chave, etapa="ok")
        except Exception as e:
            tent = est.get("tentativas", 0) + 1
            ctx.estado.set(chave, tentativas=tent)
            log.warning("agenda: falha em %s (%s)", chave, e)
            if tent == 3:
                ctx.notif.enviar("Agenda do iCloud com problema", f"Não consegui atualizar {chave}: {type(e).__name__}. Tentarei de novo.", "high")


def _salvar_documentos(ctx: Contexto, pasta, res: dict) -> str:
    docs = documentos(res)
    total = len(res.get("documentos") or [])
    salvos = 0
    if docs:
        destino = ctx.drive.subpasta(pasta, ctx.cfg, "docs")
        existentes = {f.read_bytes() for f in destino.iterdir() if f.is_file()}
        for nome, dados in docs:
            if dados not in existentes:          # nunca duplica o mesmo documento
                ctx.drive.gravar_unico(destino, nome, dados)
                existentes.add(dados)
                salvos += 1
    faltou = f" ({total - len(docs)} não baixaram)" if total and total != len(docs) else ""
    return (f"{len(docs)} documento(s) salvos" if docs else "sem documentos") + faltou


def _convocacao_completa(ctx: Contexto, msg, c, mid: str, est: dict) -> Optional[Resultado]:
    """Uma OS por vez: busca no SIOPI, salva pastas e documentos e SÓ ENTÃO insere a linha completa na planilha."""
    nova, avisos = preparar_os(c, msg, ctx.plan, ctx.hoje, ctx.cfg)          # valida antes de gastar uma busca
    if nova is None:
        _avisar(ctx, mid, "nao_aplicado", f"Não processei: convocação {c.os_numero}", "; ".join(avisos))
        return None
    res, motivo = (None, "offline") if ctx.siopi_fora else ctx.siopi.buscar(c.os_numero, sem_imagem=any(n.lower().endswith(".txt") for n, _ in msg.anexos))
    sem_siopi = res is None
    if sem_siopi:
        if motivo == "offline":
            ctx.siopi_fora = True
        tent = est.get("tentativas_siopi", 0) + 1
        ctx.estado.set(mid, tentativas_siopi=tent)
        if tent < ctx.tentativas_max or not ctx.permitir_sem_siopi:
            _avisar(ctx, mid, f"siopi{tent}", f"SIOPI sem resposta: OS {c.os_numero} aguardando",
                    f"O agente do SIOPI não respondeu ({motivo}). A OS NÃO foi criada; tentarei de novo na próxima rodada.")
            return None
    nova, avisos = preparar_os(c, msg, ctx.plan, ctx.hoje, ctx.cfg)          # recalcula o item: a planilha pode ter mudado
    if nova is None:
        _avisar(ctx, mid, "nao_aplicado", f"Não processei: convocação {c.os_numero}", "; ".join(avisos))
        return None
    resumo = ""
    if not sem_siopi:
        novos, av = campos_planilha(res, nova.campos)
        nova.campos.update(novos)
        nova.avisos += av
    else:
        nova.avisos.append("criada SEM os dados do SIOPI: use 'Obter dados' no dashboard")
    pasta = ctx.drive.criar_estrutura(nova, ctx.cfg, msg)                    # pastas e documentos antes da linha
    if not sem_siopi:
        resumo = " · ".join(x for x in (nova.campos.get("categoria"), nova.campos.get("tip"),
                                         f"matrícula {nova.campos['matricula']}" if nova.campos.get("matricula") else "",
                                         _salvar_documentos(ctx, pasta, res)) if x)
    ctx.plan.adicionar(nova.campos)                                          # a linha só entra quando tudo está pronto
    if sem_siopi:
        ctx.estado.set("siopi:" + c.os_numero, etapa="pendente", tentativas=0)
    return Resultado(True, "criada", nova.campos, nova.avisos, nova_os=nova, pode_mover_email=True, resumo=resumo,
                     agenda=ops_nova_os(c.os_numero, nova.campos))


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
                      nova_os=nova, pode_mover_email=True, agenda=est.get("agenda", []))
    else:
        if c.tipo == "convocacao" and ctx.siopi is not None:
            r = _convocacao_completa(ctx, msg, c, mid, est)
            if r is None:
                return
        else:
            r = aplicar(c, msg, ctx.plan, ctx.regras, ctx.hoje, ctx.cfg)
        if not r.aplicado:
            _avisar(ctx, mid, "nao_aplicado", f"Não processei: {c.tipo} {c.os_numero or ''}", "; ".join(r.avisos))
            return
        ctx.estado.set(mid, etapa="aplicado", acao=r.acao, avisos=r.avisos, arquivos=r.arquivos,
                       nova=asdict(r.nova_os) if r.nova_os else None, agenda=r.agenda)

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
    _enfileirar_agenda(ctx, r.agenda)
    sincronizar_agenda(ctx)
    _notificar_sucesso(ctx, c.tipo, c.os_numero, r)


def _aplicar_siopi(ctx: Contexto, os_numero: str, res: dict) -> None:
    achadas = ctx.plan.achar_os(os_numero)
    if len(achadas) != 1:
        raise RuntimeError("OS não encontrada (ou duplicada) na planilha ao aplicar o SIOPI")
    linha = achadas[0]
    novos, avisos = campos_planilha(res, linha)
    if novos:
        ctx.plan.atualizar(linha["ri"], novos)
    docs = documentos(res)
    pasta = ctx.drive.achar_pasta_os(os_numero)
    salvos = 0
    if pasta and docs:
        destino = ctx.drive.subpasta(pasta, ctx.cfg, "docs")
        existentes = {f.read_bytes() for f in destino.iterdir() if f.is_file()}
        for nome, dados in docs:
            if dados not in existentes:          # nunca duplica o mesmo documento
                ctx.drive.gravar_unico(destino, nome, dados)
                salvos += 1
    elif docs:
        avisos.append("pasta da OS não encontrada para salvar os documentos do SIOPI")
    total = len(res.get("documentos") or [])
    if total and total != len(docs):
        avisos.append(f"{total - len(docs)} documento(s) do SIOPI não baixaram")
    partes = [x for x in (novos.get("categoria"), novos.get("tip"), f"matrícula {novos['matricula']}" if novos.get("matricula") else "") if x]
    partes.append(f"{salvos} documento(s) salvos" if docs else "sem documentos")
    texto = " · ".join(partes) + ("\n⚠ " + "\n⚠ ".join(avisos) if avisos else "")
    ctx.notif.enviar(f"OS {linha.get('item', '')} completada pelo SIOPI", texto, "high" if avisos else "default")


def completar_siopi(ctx: Contexto) -> None:
    """Passo curto por OS pendente: faz o pedido, ou lê a resposta, ou desiste depois de algumas tentativas."""
    for chave, est in ctx.estado.itens("siopi:"):
        os_numero, etapa = chave[len("siopi:"):], est.get("etapa")
        if etapa not in ("pendente", "aguardando"):
            continue
        try:
            if etapa == "pendente":
                pid = ctx.siopi.pedir(os_numero, sem_imagem=True)
                ctx.estado.set(chave, etapa="aguardando", pedido=pid, enviado=ctx.agora().isoformat())
                continue
            pid = est["pedido"]
            existe, res = ctx.siopi.resposta(pid)
            if res:
                _aplicar_siopi(ctx, os_numero, res)
                ctx.siopi.limpar(pid)
                ctx.estado.set(chave, etapa="completo")
                continue
            idade = (ctx.agora() - datetime.fromisoformat(est["enviado"])).total_seconds()
            if idade > (ctx.espera_total_s if existe else ctx.espera_resposta_s):
                ctx.siopi.limpar(pid)
                tent = est.get("tentativas", 0) + 1
                if tent >= ctx.tentativas_max:
                    ctx.estado.set(chave, etapa="desistiu", tentativas=tent)
                    ctx.notif.enviar(f"SIOPI não respondeu para a OS {os_numero}",
                                     "Confira se o agente do SIOPI está ligado e use 'Obter dados' no dashboard.", "high")
                else:
                    ctx.estado.set(chave, etapa="pendente", tentativas=tent)
        except Exception:
            log.exception("falha ao completar com o SIOPI: %s", os_numero)


LOTE = 5   # acima disso, os avisos comuns viram um resumo só


def rodar_uma_vez(ctx: Contexto) -> int:
    n = 0
    ctx.siopi_fora = False
    mensagens = ordenar_cronologicamente(ctx.caixa.listar())
    real, coletor = ctx.notif, None
    if len(mensagens) > LOTE:
        coletor = ctx.notif = NotificadorColetor(real)
    try:
        for uid, msg in mensagens:
            try:
                processar(ctx, uid, msg)
                n += 1
            except Exception:
                log.exception("erro inesperado no e-mail %s", uid)
        if ctx.siopi is not None:
            completar_siopi(ctx)
        sincronizar_agenda(ctx)
    finally:
        ctx.notif = real
        if coletor:
            coletor.fechar(n)
    return n
