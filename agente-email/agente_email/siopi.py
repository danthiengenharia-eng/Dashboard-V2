"""Completa a OS com os dados do SIOPI, pelo mesmo protocolo que o dashboard usa.

O dashboard grava `siopi_pedido_<id>.json` na pasta Laudos; o agente do SIOPI (no computador) responde com
`siopi_resposta_<id>.json`. Aqui o pedido e a leitura da resposta são separados em passos curtos, para a
rodada de 5 minutos nunca ficar esperando o SIOPI.
"""
import base64
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .convocacao import title_case
from .texto import normalizar

import re

TIPOLOGIAS_PADRAO = ["Apartamento", "Casa", "Casa comercial", "Obra Residencial", "Terreno", "Sala comercial", "Loja", "Gleba"]
_REGRAS = [(re.compile(r"\b(?:apartamento|apto|apt|ap)\b\.? ?(?:n[o.]* ?)?\d"), "Apartamento"),
           (re.compile(r"\bloja\b\.? ?(?:n[o.]* ?)?\d"), "Loja"),
           (re.compile(r"\bsala\b\.? ?(?:n[o.]* ?)?\d"), "Sala comercial")]


def tipologia_siopi(r: dict, opcoes: List[str]) -> Tuple[str, str]:
    """Espelha tipologiaSIOPI() do dashboard. Devolve (tipologia, aviso)."""
    n = normalizar
    opcao = lambda nome: next((o for o in opcoes if n(o) == n(nome)), None)
    alvos = [n(x) for x in (r.get("tipo_construcao"), r.get("tipologia"), r.get("tipo_imovel")) if n(x or "")]
    pela_base = ""
    maiores = sorted([o for o in opcoes if n(o)], key=lambda o: len(n(o)), reverse=True)
    for alvo in alvos:
        pela_base = (opcao(alvo) or next((o for o in maiores if n(o) in alvo), None)
                     or next((o for o in reversed(maiores) if alvo in n(o)), None) or "")
        if pela_base:
            break
    for fonte in (r.get("complemento"), r.get("endereco")):
        for regra, nome in _REGRAS:
            if regra.search(n(fonte or "")) and opcao(nome):
                diverge = bool(pela_base) and n(pela_base) != n(nome)
                aviso = f'o complemento indica "{nome}", mas o SIOPI marca construção "{r.get("tipo_construcao") or r.get("tipo_imovel")}"' if diverge else ""
                return opcao(nome), aviso
    return pela_base, ""


def campos_planilha(r: dict, atuais: Dict[str, str], opcoes_tip: Optional[List[str]] = None) -> Tuple[Dict[str, str], List[str]]:
    """Campos que o SIOPI preenche na linha da OS (como o botão 'Obter dados' do dashboard) e avisos."""
    novos: Dict[str, str] = {}
    avisos: List[str] = []
    if r.get("endereco"):
        novos["end"] = title_case(r["endereco"])
    if r.get("bairro"):
        novos["bairro"] = title_case(r["bairro"])
    if r.get("cep"):
        novos["cep"] = r["cep"]
    if r.get("area_privativa"):
        a = str(r["area_privativa"])
        novos["area"] = a if re.search("m", a, re.I) else a + " m²"
    tip, aviso = tipologia_siopi(r, opcoes_tip or TIPOLOGIAS_PADRAO)
    if tip:
        novos["tip"] = tip
    if aviso:
        avisos.append("Tipologia: " + aviso)
    for chave, campo in (("matricula", "matricula"), ("cnm", "cnm"), ("categoria", "categoria"), ("data_abertura", "abr")):
        if r.get(chave):
            novos[campo] = str(r[chave])
    if r.get("valor_compra_venda"):
        novos["vcv"] = "R$ " + str(r["valor_compra_venda"])
    # município e atividade definem valores e polo: só avisa se divergirem, não troca sozinho
    if r.get("municipio") and normalizar(r["municipio"]) != normalizar(str(atuais.get("mun", "")).replace("(Deslocamento especial)", "")):
        avisos.append(f"Município no SIOPI ({title_case(r['municipio'])}) difere do da OS ({atuais.get('mun')})")
    if r.get("atividade_extraida") and normalizar(r["atividade_extraida"]).replace(" ", "") != normalizar(str(atuais.get("atv", ""))).replace(" ", ""):
        avisos.append(f"Atividade no SIOPI ({r['atividade_extraida']}) difere da OS ({atuais.get('atv')})")
    return novos, avisos


def documentos(r: dict) -> List[Tuple[str, bytes]]:
    saida = []
    for d in r.get("documentos") or []:
        if d.get("bytes") and d.get("nome"):
            saida.append((d["nome"], base64.b64decode(d["bytes"])))
    return saida


class SiopiArquivos:
    """Pedido e resposta por arquivos na pasta Laudos (sincronizada pelo Drive para desktop)."""

    def __init__(self, raiz):
        self.raiz = Path(raiz)

    def pedir(self, os_numero: str, sem_imagem: bool = True) -> str:
        pid = format(int(time.time() * 1000), "x") + secrets.token_hex(3)
        dados = {"versao": 1, "id": pid, "criado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "os": os_numero.strip(),
                 "atividade": "", "data_abertura": "", "sem_imagem": sem_imagem}
        self.raiz.mkdir(parents=True, exist_ok=True)
        (self.raiz / f"siopi_pedido_{pid}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return pid

    def resposta(self, pid: str) -> Tuple[bool, Optional[dict]]:
        """(arquivo_existe, resultado se pronto)."""
        arq = self.raiz / f"siopi_resposta_{pid}.json"
        if not arq.exists():
            return False, None
        try:
            d = json.loads(arq.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError):      # ainda sincronizando
            return True, None
        if d.get("id") == pid and d.get("estado") == "pronto" and d.get("resultado"):
            return True, d["resultado"]
        return True, None

    def limpar(self, pid: str):
        for nome in (f"siopi_pedido_{pid}.json", f"siopi_resposta_{pid}.json"):
            try:
                (self.raiz / nome).unlink()
            except OSError:
                pass
