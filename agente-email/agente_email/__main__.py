"""Uso:  python -m agente_email --uma-vez   |   python -m agente_email --loop"""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
from pathlib import Path

from .agente import PASTAS_PADRAO, Contexto, rodar_uma_vez
from datetime import date, timedelta

from .agenda import AgendaIcloud
from .caixa import CaixaImap
from .classificador import classificar
from .convocacao import decodificar, interpretar
from .config import Configuracao
from .drive import DriveLocal
from .estado import Estado
from .notificar import NotificadorNulo, NtfyNotificador
from .planilha import PlanilhaGoogle
from .siopi import SiopiArquivos, reiniciar_pendentes
from .status import NotificadorRegistro, Status


def carregar_env(caminho: str = ".env"):
    p = Path(caminho)
    if not p.exists():
        return
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def exigir(nome: str) -> str:
    v = os.environ.get(nome)
    if not v:
        sys.exit(f"Falta {nome} no arquivo .env (veja .env.exemplo)")
    return v


def data_inicio() -> date:
    """DESDE=AAAA-MM-DD: só e-mails a partir desse dia são processados (protege os e-mails antigos)."""
    v = exigir("DESDE")
    try:
        return date.fromisoformat(v)
    except ValueError:
        sys.exit("DESDE precisa estar no formato AAAA-MM-DD, por exemplo DESDE=2026-11-28")


def simular():
    from .ensaio import descrever
    caixa = CaixaImap(exigir("IMAP_SERVIDOR"), exigir("IMAP_USUARIO"), exigir("IMAP_SENHA"), desde=data_inicio())
    try:
        msgs = caixa.listar()
        print(f"{len(msgs)} e-mail(s) da CEF desde {data_inicio():%d/%m/%Y}. NADA será alterado neste modo.")
        cfg = plan = None
        try:
            cfg = Configuracao.carregar(exigir("CONFIG_DASHBOARD"))
            plan = PlanilhaGoogle(cfg.planilha_id, cfg.aba, exigir("GOOGLE_SA_JSON"), cfg.colunas)
            plan.listar()
            print(f"Planilha conferida (somente leitura): {cfg.aba}\n")
        except (Exception, SystemExit) as e:
            plan = None
            print(f"(Não consegui ler a planilha: {type(e).__name__}. Mostrando só a classificação.)\n")
        for linha in descrever(msgs, plan, cfg, date.today()):
            print(linha)
    finally:
        caixa.fechar()


def montar() -> Contexto:
    cfg = Configuracao.carregar(exigir("CONFIG_DASHBOARD"))
    ajustes = json.loads(Path(os.environ.get("CONFIG_AGENTE", "config.json")).read_text(encoding="utf-8")) if Path(os.environ.get("CONFIG_AGENTE", "config.json")).exists() else {}
    caixa = CaixaImap(exigir("IMAP_SERVIDOR"), exigir("IMAP_USUARIO"), exigir("IMAP_SENHA"), desde=data_inicio())
    plan = PlanilhaGoogle(cfg.planilha_id, cfg.aba, exigir("GOOGLE_SA_JSON"), cfg.colunas)
    notif = (NtfyNotificador(os.environ.get("NTFY_SERVIDOR", "https://ntfy.sh"), os.environ["NTFY_TOPICO"], os.environ.get("NTFY_TOKEN", ""))
             if os.environ.get("NTFY_TOPICO") else NotificadorNulo())
    pastas = {**PASTAS_PADRAO, **{k: v for k, v in (ajustes.get("pastas_imap") or {}).items() if k in PASTAS_PADRAO}}
    agenda = (AgendaIcloud(os.environ["ICLOUD_USUARIO"], exigir("ICLOUD_SENHA"), os.environ.get("ICLOUD_CALENDARIO", "Entregas OS"))
              if os.environ.get("ICLOUD_USUARIO") else None)
    return Contexto(caixa, plan, DriveLocal(exigir("PASTA_LAUDOS")), notif, cfg, Estado(os.environ.get("ESTADO", "saida/estado.json")),
                    ajustes.get("regras", {}), pastas,
                    siopi=None if os.environ.get("SIOPI", "1") == "0" else SiopiArquivos(os.environ.get("SIOPI_PASTA") or exigir("PASTA_LAUDOS")),
                    permitir_sem_siopi=os.environ.get("SIOPI_OBRIGATORIO", "0") != "1", agenda=agenda)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uma-vez", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--refazer-siopi", action="store_true", help="refaz o pedido ao SIOPI das OS que ficaram sem os dados")
    ap.add_argument("--simular", action="store_true", help="mostra o que faria com os e-mails, sem alterar nada")
    ap.add_argument("--testar-email", action="store_true", help="descobre o servidor IMAP e confere as pastas")
    ap.add_argument("--intervalo", type=int, default=5, help="minutos entre rodadas (padrão 5)")
    a = ap.parse_args()
    carregar_env()
    if a.testar_email:
        from .caixa import testar_conexao
        for linha in testar_conexao(exigir("IMAP_USUARIO"), exigir("IMAP_SENHA"), os.environ.get("IMAP_SERVIDOR", ""),
                                    esperadas=[v for v in PASTAS_PADRAO.values() if v]):
            print(linha)
        return
    if a.simular:
        simular()
        return
    if a.refazer_siopi:
        n = reiniciar_pendentes(Estado(os.environ.get("ESTADO", "saida/estado.json")))
        for f in Path(os.environ.get("SIOPI_PASTA") or os.environ.get("PASTA_LAUDOS", ".")).glob("siopi_pedido_*.json"):
            f.unlink()
        print(f"{n} OS voltaram para a fila do SIOPI. Rode --uma-vez para refazer os pedidos.")
        return
    data_inicio()   # exige DESDE antes de qualquer alteração
    Path("saida").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=([logging.StreamHandler()] if sys.stderr else []) + [RotatingFileHandler(os.environ.get("LOG", "saida/agente.log"), maxBytes=5_000_000, backupCount=3, encoding="utf-8")])
    raiz_drive = os.environ.get("SIOPI_PASTA") or os.environ.get("PASTA_LAUDOS")
    st = Status("saida", raiz_drive)
    st.iniciar()
    code = 0
    try:
        while True:
            st.processar_comandos()
            if st.parar:
                break
            if st.reiniciar:
                code = 1                      # o Agendador de Tarefas reinicia o agente em 1 minuto
                break
            if not st.pausado:
                ctx = None
                st.estado, st.detalhe = "trabalhando", "lendo a caixa de e-mail"
                st.bater()
                try:
                    ctx = montar()
                    ctx.status = st
                    ctx.notif = NotificadorRegistro(ctx.notif, st)
                    ctx.estado.podar()
                    n = rodar_uma_vez(ctx)
                    logging.info("rodada concluída: %d e-mail(s)", n)
                    st.rodada_ok(n)
                except SystemExit as e:
                    st.falha(str(e) or "configuração incompleta")
                    raise
                except Exception as e:
                    logging.exception("falha na rodada (conexão ou configuração); tentarei de novo")
                    st.falha(f"falha na rodada: {type(e).__name__}")
                finally:
                    if ctx:
                        ctx.caixa.fechar()
                    st.estado, st.detalhe = "ocioso", ""
            if not a.loop:
                break
            espera = a.intervalo * 60
            st.proxima_em = (st.relogio() + timedelta(seconds=espera)).isoformat(timespec="seconds")
            st.acordar.clear()
            st.bater()
            while espera > 0 and not st.acordar.is_set():
                time.sleep(min(5, espera))
                espera -= 5
                if st.processar_comandos() and (st.parar or st.reiniciar):
                    break
            st.proxima_em = None
    finally:
        st.encerrar()
    sys.exit(code)


if __name__ == "__main__":
    main()
