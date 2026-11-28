"""Memória do agente: o que já foi feito com cada e-mail, para nunca repetir nem avisar em dobro."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path


class Estado:
    def __init__(self, caminho=None):
        self.caminho = Path(caminho) if caminho else None
        self.d = {}
        if self.caminho and self.caminho.exists():
            self.d = json.loads(self.caminho.read_text(encoding="utf-8"))

    def _salvar(self):
        if not self.caminho:
            return
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.caminho)

    def get(self, mid: str) -> dict:
        return self.d.get(mid, {})

    def set(self, mid: str, **dados):
        self.d.setdefault(mid, {}).update(dados)
        self.d[mid]["ts"] = datetime.now().isoformat(timespec="seconds")
        self._salvar()

    def primeira_vez(self, mid: str, chave: str) -> bool:
        """True só na primeira vez que um aviso `chave` é dado para este e-mail."""
        avisados = self.d.setdefault(mid, {}).setdefault("avisos", [])
        if chave in avisados:
            return False
        avisados.append(chave)
        self._salvar()
        return True

    def itens(self, prefixo: str):
        return [(k, dict(v)) for k, v in self.d.items() if k.startswith(prefixo)]

    def podar(self, dias: int = 365) -> int:
        """Esquece e-mails concluídos há mais de `dias` (já saíram da caixa). Nunca mexe no que está em andamento."""
        limite = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
        velhos = [k for k, v in self.d.items() if v.get("etapa") in ("completo", "ok", "desistiu") and v.get("ts", "9999") < limite]
        for k in velhos:
            del self.d[k]
        if velhos:
            self._salvar()
        return len(velhos)
