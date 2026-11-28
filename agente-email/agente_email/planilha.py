"""Acesso à planilha de OS atrás de uma interface simples.

Hoje o destino é a planilha do Google; amanhã pode ser outro banco, trocando só esta camada.
Os índices de coluna seguem o dashboard (_COL_DEFAULTS) e podem ser sobrescritos por CFG.COLS.
"""
from typing import Dict, List, Optional

COL_PADRAO = {
    "item": 0, "os": 1, "aceita": 2, "atv": 3, "tv": 4, "polo": 5, "mun": 6, "bairro": 7, "tip": 8,
    "end": 9, "area": 10, "cep": 11, "mes": 12, "siopi": 13, "pept": 14, "ent": 15, "vis": 16,
    "lau": 17, "vos": 20, "fich": 21, "vd": 22, "vt": 23, "st": 24, "va": 25, "rsm": 26, "rev": 27,
    "abr": 28, "prz": 29, "matricula": 30, "cnm": 31, "vcv": 32, "alertaMat": 33, "categoria": 34,
}


def letra_coluna(i: int) -> str:
    s = ""
    while i >= 0:
        s = chr(65 + i % 26) + s
        i = i // 26 - 1
    return s


class Planilha:
    """Interface. `os` é o número da OS sem barras de formatação especial, como na planilha."""

    def listar(self) -> List[Dict]:  # cada item traz 'ri' (linha, base 1) e os campos
        raise NotImplementedError

    def atualizar(self, ri: int, campos: Dict[str, str]) -> None:
        raise NotImplementedError

    def adicionar(self, campos: Dict[str, str]) -> int:
        raise NotImplementedError

    def achar_os(self, numero_os: str) -> List[Dict]:
        alvo = _chave(numero_os)
        return [r for r in self.listar() if _chave(r.get("os", "")) == alvo]


def _chave(os_numero: str) -> str:
    return (os_numero or "").replace("/", "").strip()


class PlanilhaMemoria(Planilha):
    """Implementação em memória, usada nos testes e em ensaios sem tocar na planilha real."""

    def __init__(self, linhas: Optional[List[Dict]] = None):
        self.linhas = [dict(l) for l in (linhas or [])]
        for i, l in enumerate(self.linhas):
            l["ri"] = i + 2  # linha 1 = cabeçalho

    def listar(self):
        return [dict(l) for l in self.linhas]

    def atualizar(self, ri, campos):
        for l in self.linhas:
            if l["ri"] == ri:
                l.update(campos)
                return
        raise KeyError(ri)

    def adicionar(self, campos):
        ri = max([l["ri"] for l in self.linhas] + [1]) + 1
        self.linhas.append({**campos, "ri": ri})
        return ri


class PlanilhaGoogle(Planilha):
    """Planilha do Google via API REST, com conta de serviço (chave JSON fora do repositório)."""

    ESCOPO = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self, planilha_id: str, aba: str, caminho_chave: str, colunas: Optional[Dict[str, int]] = None, sessao=None):
        self.id, self.aba = planilha_id, aba
        self.col = {**COL_PADRAO, **(colunas or {})}
        if sessao is None:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
            cred = service_account.Credentials.from_service_account_file(caminho_chave, scopes=self.ESCOPO)
            sessao = AuthorizedSession(cred)
        self.s = sessao
        self.base = f"https://sheets.googleapis.com/v4/spreadsheets/{planilha_id}/values"

    def _ultima(self) -> str:
        return letra_coluna(max(self.col.values()))

    def listar(self):
        r = self.s.get(f"{self.base}/{self.aba}!A2:{self._ultima()}", params={"valueRenderOption": "FORMATTED_VALUE"})
        r.raise_for_status()
        inv = {i: k for k, i in self.col.items()}
        saida = []
        for n, linha in enumerate(r.json().get("values", []), start=2):
            d = {inv[i]: v for i, v in enumerate(linha) if i in inv}
            d["ri"] = n
            saida.append(d)
        return saida

    def atualizar(self, ri, campos):
        dados = [{"range": f"{self.aba}!{letra_coluna(self.col[k])}{ri}", "values": [[v]]} for k, v in campos.items()]
        r = self.s.post(f"{self.base}:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": dados})
        r.raise_for_status()

    def adicionar(self, campos):
        ri = max([l["ri"] for l in self.listar()] + [1]) + 1
        linha = [""] * (max(self.col.values()) + 1)
        for k, v in campos.items():
            linha[self.col[k]] = v
        r = self.s.put(f"{self.base}/{self.aba}!A{ri}:{self._ultima()}{ri}", params={"valueInputOption": "USER_ENTERED"}, json={"values": [linha]})
        r.raise_for_status()
        return ri
