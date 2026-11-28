# Janela de status do agente (Windows). Dê dois cliques para abrir; pode fechar sem afetar o agente.
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
os.chdir(BASE)
from agente_email.status import enviar_comando, ler_status, resumo_painel  # noqa: E402

CORES = {"verde": "#16a34a", "amarelo": "#ca8a04", "vermelho": "#dc2626", "cinza": "#6b7280"}
SAIDA = BASE / "saida"
TAREFA = "AgenteEmailDanthi"

raiz = tk.Tk()
raiz.title("Agente de e-mail · Danthi")
raiz.geometry("520x470")
raiz.configure(padx=14, pady=10)

topo = tk.Frame(raiz)
topo.pack(fill="x")
bola = tk.Canvas(topo, width=34, height=34, highlightthickness=0)
bola.pack(side="left")
circulo = bola.create_oval(3, 3, 31, 31, fill=CORES["cinza"], outline="")
titulo = tk.Label(topo, text="…", font=("Segoe UI", 18, "bold"))
titulo.pack(side="left", padx=10)
info = tk.Label(raiz, text="", justify="left", anchor="w", font=("Segoe UI", 10), wraplength=480)
info.pack(fill="x", pady=(8, 4))
tk.Label(raiz, text="Atividade recente", anchor="w", font=("Segoe UI", 9, "bold")).pack(fill="x")
lista = tk.Listbox(raiz, height=10, font=("Consolas", 9))
lista.pack(fill="both", expand=True, pady=(2, 8))


def comando(nome):
    enviar_comando(nome, SAIDA)
    raiz.after(1500, atualizar)


def tarefa(acao):
    subprocess.Popen(["schtasks", acao, "/TN", TAREFA], creationflags=0x08000000)
    raiz.after(3000, atualizar)


botoes = tk.Frame(raiz)
botoes.pack(fill="x")
for texto, f in (("Pausar", lambda: comando("pausar")), ("Retomar", lambda: comando("retomar")),
                 ("Rodar agora", lambda: comando("rodar_agora")), ("Limpar alerta", lambda: comando("limpar_alerta"))):
    tk.Button(botoes, text=texto, command=f, width=12).pack(side="left", padx=2, pady=2)
botoes2 = tk.Frame(raiz)
botoes2.pack(fill="x")
for texto, f in (("Ligar agente", lambda: tarefa("/Run")), ("Desligar agente", lambda: tarefa("/End")),
                 ("Abrir log", lambda: os.startfile(SAIDA / "agente.log") if (SAIDA / "agente.log").exists() else None),
                 ("Pasta saida", lambda: os.startfile(SAIDA) if SAIDA.exists() else None)):
    tk.Button(botoes2, text=texto, command=f, width=12).pack(side="left", padx=2, pady=2)


def atualizar():
    d = ler_status(SAIDA)
    r = resumo_painel(d)
    bola.itemconfig(circulo, fill=CORES.get(r["cor"], CORES["cinza"]))
    titulo.config(text=r["titulo"])
    info.config(text="\n".join(r["linhas"]))
    lista.delete(0, "end")
    for linha in reversed((d or {}).get("log", [])):
        lista.insert("end", linha)
    raiz.after(3000, atualizar)


atualizar()
raiz.mainloop()
