"""Valida o reconhecimento com .msg salvos.  Uso: python scripts/validar_msg.py PASTA"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agente_email.classificador import classificar
from agente_email.convocacao import decodificar, interpretar
from agente_email.eventos import interpretar_conclusao
from agente_email.leitor_msg import ler_msg

for arq in sorted(glob.glob(os.path.join(sys.argv[1], "*.msg"))):
    m = ler_msg(arq)
    c = classificar(m)
    print(f"{c.tipo:13} OS={c.os_numero} avisos={c.avisos} anexos={[n for n,_ in m.anexos]}")
    if c.tipo == "convocacao":
        txt = next((decodificar(d) for n, d in m.anexos if n.lower().endswith(".txt")), m.corpo)
        campos = interpretar(txt)
        print("   ", {k: v for k, v in campos.items() if k not in ("contato_nome", "contato_telefone")})
    if c.tipo == "conclusao":
        print("   ", interpretar_conclusao(m.corpo))
