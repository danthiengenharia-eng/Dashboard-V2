"""Pastas e arquivos das OS, pelo Drive para desktop (a pasta Laudos aparece como pasta do computador)."""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import Configuracao
from .criar_os import NovaOS
from .modelos import Mensagem

SUBPASTAS_PADRAO = [{"nm": "01 - Convocação", "role": "txt"}, {"nm": "02 - Documentos", "role": "docs"},
                    {"nm": "03 - Rel. Fotográfico", "role": "fotos"}, {"nm": "04 - Produtos", "role": "pdf"},
                    {"nm": "05 - Ficha de pesquisa", "role": "geral"}]


def _nome_seguro(nome: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome).strip() or "arquivo"


def _livre(pasta: Path, nome: str) -> Path:
    destino = pasta / nome
    n = 1
    while destino.exists():
        destino = pasta / f"{destino.stem.split(' (')[0]} ({n}){Path(nome).suffix}"
        n += 1
    return destino


class DriveLocal:
    def __init__(self, raiz):
        self.raiz = Path(raiz)

    def criar_estrutura(self, nova: NovaOS, cfg: Configuracao, msg: Mensagem) -> Path:
        """Cria mês/OS/subpastas e arquiva o .txt e o e-mail original. Pode ser repetido sem duplicar."""
        pasta_os = self.raiz / nova.pasta_mes / nova.pasta_os
        subs = cfg.subpastas or SUBPASTAS_PADRAO
        pastas = {}
        for sp in subs:
            d = pasta_os / sp["nm"]
            d.mkdir(parents=True, exist_ok=True)
            pastas.setdefault(sp.get("role"), d)
        pasta_os.mkdir(parents=True, exist_ok=True)
        destino_txt = pastas.get("txt", pasta_os) if cfg.txt_destino == "convocacao" else pasta_os

        c = nova.campos
        for nome, dados in msg.anexos:
            if not nome.lower().endswith(".txt"):
                continue
            original = Path(nome).stem
            osp = c["os"]
            alvo = (cfg.txt_nome.replace("{nr}", c["item"]).replace("{atv}", c["atv"])
                    .replace("{os}", osp.replace(".", "")).replace("{osb}", osp).replace("{original}", original))
            if not alvo.lower().endswith(".txt"):
                alvo += ".txt"
            alvo = _nome_seguro(alvo)
            if not any(f.name.startswith(Path(alvo).stem) for f in destino_txt.glob("*.txt")):
                _livre(destino_txt, alvo).write_bytes(dados)
            break
        if msg.bruto and not (pastas.get("txt", pasta_os) / "email_convocacao.eml").exists():
            (pastas.get("txt", pasta_os) / "email_convocacao.eml").write_bytes(msg.bruto)
        return pasta_os

    def achar_pasta_os(self, os_numero: str) -> Optional[Path]:
        osp = os_numero.replace("/", "")
        chaves = {osp, osp.replace(".", "")}
        for mes in sorted((d for d in self.raiz.iterdir() if d.is_dir()), reverse=True) if self.raiz.exists() else []:
            for d in mes.iterdir():
                if d.is_dir() and any(d.name.endswith(k) or k in d.name for k in chaves):
                    return d
        return None

    def gravar_json(self, os_numero: str, nome: str, dados: dict) -> Optional[Path]:
        pasta = self.achar_pasta_os(os_numero)
        if not pasta:
            return None
        destino = pasta / nome
        destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return destino

    def sinalizar_pept(self, os_numero: str, assunto: str) -> bool:
        return self.gravar_json(os_numero, "pept_resposta.json", {
            "os": os_numero, "situacao": "resolvida_pela_caixa", "assunto": assunto,
            "recebido_em": datetime.now().isoformat(timespec="seconds"), "conferido": False}) is not None

    def subpasta(self, pasta_os: Path, cfg: Configuracao, papel: str) -> Path:
        for sp in (cfg.subpastas or SUBPASTAS_PADRAO):
            if sp.get("role") == papel:
                d = pasta_os / sp["nm"]
                d.mkdir(parents=True, exist_ok=True)
                return d
        return pasta_os

    @staticmethod
    def gravar_unico(pasta: Path, nome: str, dados: bytes) -> Path:
        """Grava sem sobrescrever: se o nome existe, vira 'nome (1).ext'."""
        pasta.mkdir(parents=True, exist_ok=True)
        destino = _livre(pasta, _nome_seguro(nome))
        destino.write_bytes(dados)
        return destino
