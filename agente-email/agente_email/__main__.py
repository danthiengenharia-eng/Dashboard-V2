"""Uso:  python -m agente_email --uma-vez   |   python -m agente_email --loop"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from .agente import PASTAS_PADRAO, Contexto, rodar_uma_vez
from datetime import date

from .caixa import CaixaImap
from .classificador import classificar
from .convocacao import decodificar, interpretar
from .config import Configuracao
from .drive import DriveLocal
from .estado import Estado
from .notificar import NotificadorNulo, NtfyNotificador
from .planilha import PlanilhaGoogle


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
    caixa = CaixaImap(exigir("IMAP_SERVIDOR"), exigir("IMAP_USUARIO"), exigir("IMAP_SENHA"), desde=data_inicio())
    try:
        msgs = caixa.listar()
        print(f"{len(msgs)} e-mail(s) da CEF desde {data_inicio():%d/%m/%Y}. NADA será alterado neste modo.\n")
        for uid, m in msgs:
            c = classificar(m)
            linha = f"{m.data:%d/%m %H:%M}  " if m.data else "              "
            linha += f"{c.tipo:13} OS {c.os_numero or '—'}"
            if c.tipo == "convocacao":
                txt = next((decodificar(d) for n, d in m.anexos if n.lower().endswith(".txt")), m.corpo)
                falta = [k for k in ("endereco", "bairro", "municipio", "cep", "atividade", "data_os") if not interpretar(txt).get(k)]
                linha += "  | dados completos" if not falta else "  | FALTAM: " + ", ".join(falta)
            if c.avisos:
                linha += "  | ⚠ " + "; ".join(c.avisos)
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
    return Contexto(caixa, plan, DriveLocal(exigir("PASTA_LAUDOS")), notif, cfg, Estado(os.environ.get("ESTADO", "saida/estado.json")),
                    ajustes.get("regras", {}), pastas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uma-vez", action="store_true")
    ap.add_argument("--loop", action="store_true")
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
    data_inicio()   # exige DESDE antes de qualquer alteração
    Path("saida").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(os.environ.get("LOG", "saida/agente.log"), encoding="utf-8")])
    while True:
        ctx = None
        try:
            ctx = montar()
            n = rodar_uma_vez(ctx)
            logging.info("rodada concluída: %d e-mail(s)", n)
        except SystemExit:
            raise
        except Exception:
            logging.exception("falha na rodada (conexão ou configuração); tentarei de novo")
        finally:
            if ctx:
                ctx.caixa.fechar()
        if not a.loop:
            break
        time.sleep(a.intervalo * 60)


if __name__ == "__main__":
    main()
