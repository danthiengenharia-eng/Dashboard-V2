"""Relatório de diagnóstico (sem senhas): versão, caminhos, arquivos, tarefa agendada e processos."""
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import __versao__


def _idade(caminho: Path) -> str:
    if not caminho.exists():
        return "NÃO EXISTE"
    seg = (datetime.now() - datetime.fromtimestamp(caminho.stat().st_mtime)).total_seconds()
    quando = f"{datetime.fromtimestamp(caminho.stat().st_mtime):%d/%m %H:%M:%S}"
    return f"{caminho.stat().st_size} bytes, modificado {quando} (há {int(seg // 60)} min {int(seg % 60)} s)"


def _cmd(args) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15, creationflags=0x08000000 if os.name == "nt" else 0)
        return (r.stdout or r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return f"(não consegui executar: {type(e).__name__})"


def gerar(saida="saida") -> str:
    saida = Path(saida)
    L = [f"VERSÃO DO CÓDIGO: {__versao__}", f"Python {platform.python_version()} · {sys.executable}", f"Pasta atual: {Path.cwd()}",
         f"Agora: {datetime.now():%d/%m/%Y %H:%M:%S}", ""]
    L.append("== .env (só se está preenchido, sem mostrar valores) ==")
    for k in ("IMAP_SERVIDOR", "IMAP_USUARIO", "IMAP_SENHA", "GOOGLE_SA_JSON", "CONFIG_DASHBOARD", "PASTA_LAUDOS", "SIOPI_PASTA",
              "NTFY_TOPICO", "ICLOUD_USUARIO", "ICLOUD_SENHA", "DESDE", "SIOPI", "SIOPI_OBRIGATORIO"):
        v = os.environ.get(k, "")
        L.append(f"  {k}: {'preenchido' if v else 'VAZIO'}" + (f" = {v}" if k in ("PASTA_LAUDOS", "SIOPI_PASTA", "CONFIG_DASHBOARD", "GOOGLE_SA_JSON", "DESDE") and v else ""))
    L.append("")
    L.append("== Caminhos ==")
    for k in ("CONFIG_DASHBOARD", "GOOGLE_SA_JSON", "PASTA_LAUDOS", "SIOPI_PASTA"):
        v = os.environ.get(k, "")
        if v:
            L.append(f"  {k}: {'existe' if Path(v).exists() else 'NÃO EXISTE'}")
    raiz = Path(os.environ.get("SIOPI_PASTA") or os.environ.get("PASTA_LAUDOS") or ".")
    L.append(f"  agente_status_email.json na pasta Laudos: {_idade(raiz / 'agente_status_email.json')}")
    pend = sorted(p.name for p in raiz.glob("siopi_*.json")) if raiz.exists() else []
    L.append(f"  pedidos/respostas do SIOPI na pasta Laudos agora: {len(pend)} {pend[:6]}")
    L.append("")
    L.append("== Pasta saida ==")
    for n in ("agente.log", "status.json", "estado.json"):
        L.append(f"  {n}: {_idade(saida / n)}")
    try:
        est = json.loads((saida / "estado.json").read_text(encoding="utf-8"))
        cont = {}
        for k, v in est.items():
            e = v.get("etapa", "?")
            cont[e] = cont.get(e, 0) + 1
        L.append(f"  estado.json por etapa: {cont}")
    except (OSError, ValueError):
        pass
    cmds = sorted(p.name for p in saida.glob("comando_*.json")) if saida.exists() else []
    L.append(f"  comandos pendentes: {len(cmds)}")
    try:
        st = json.loads((saida / "status.json").read_text(encoding="utf-8"))
        L.append(f"  status.json: estado={st.get('estado')} rotulo={st.get('rotulo')} batimento={st.get('batimento_em')} detalhe={st.get('detalhe')!r}")
    except (OSError, ValueError):
        pass
    try:
        linhas = (saida / "agente.log").read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
        L += ["", "== Últimas linhas do agente.log =="] + ["  " + x for x in linhas] if linhas else ["", "== agente.log está VAZIO =="]
    except OSError:
        L += ["", "== agente.log não existe =="]
    if os.name == "nt":
        L += ["", "== Tarefa agendada =="] + ["  " + x for x in _cmd(["schtasks", "/Query", "/TN", "AgenteEmailDanthi", "/FO", "LIST"]).splitlines()[:10]]
        L += ["", "== Processos python =="] + ["  " + x for x in _cmd(["tasklist", "/FI", "IMAGENAME eq pythonw.exe"]).splitlines()[-4:]]
        L += ["  " + x for x in _cmd(["tasklist", "/FI", "IMAGENAME eq python.exe"]).splitlines()[-4:]]
    return "\n".join(L)
