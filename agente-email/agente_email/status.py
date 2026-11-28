"""Estado do agente: batimento a cada 30 s (arquivo local + painel "Agentes" do dashboard) e comandos (pausar, retomar...)."""
import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .notificar import Notificador

AGENTE = "email"
VALIDADE_S = 150            # sem batimento por mais que isso = offline
COMANDOS = {"pausar", "retomar", "reiniciar", "forcar_reinicio", "limpar_alerta", "rodar_agora", "parar"}


def _agora() -> datetime:
    return datetime.now().astimezone()


def _escrever(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, caminho)


class Status:
    def __init__(self, saida="saida", drive: Optional[str] = None, relogio=_agora, intervalo_s: int = 30):
        self.saida = Path(saida)
        self.drive = Path(drive) if drive else None
        self.relogio, self.intervalo_s = relogio, intervalo_s
        self.estado, self.detalhe, self.pausado, self.alerta = "ocioso", "", False, ""
        self.eventos: List[str] = []
        self.ultima_rodada: Optional[dict] = None
        self.proxima_em: Optional[str] = None
        self.acordar = threading.Event()
        self.reiniciar = self.parar = False
        self._parar_thread = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ----- o que o agente informa -----
    def evento(self, texto: str) -> None:
        with self._lock:
            self.eventos = (self.eventos + [f"{self.relogio():%d/%m %H:%M}  {texto}"])[-30:]

    def rodada_ok(self, n: int) -> None:
        with self._lock:
            self.ultima_rodada = {"quando": self.relogio().isoformat(timespec="seconds"), "emails": n}
            self.alerta = ""

    def falha(self, texto: str) -> None:
        with self._lock:
            self.alerta = texto
        self.evento("⚠ " + texto)

    # ----- batimento -----
    def dados(self) -> dict:
        with self._lock:
            offline = self.estado == "desligado"
            cor = "vermelho" if self.alerta else "amarelo" if self.pausado else "verde"
            rotulo = ("Desligado" if offline else "Com problema" if self.alerta else "Pausado" if self.pausado
                      else "Trabalhando" if self.estado == "trabalhando" else "Online")
            return {"agente": AGENTE, "nome": "Agente de e-mail", "estado": self.estado, "rotulo": rotulo, "cor": cor,
                    "batimento_em": self.relogio().isoformat(timespec="seconds"), "validade_s": VALIDADE_S,
                    "pausado": self.pausado, "alerta": self.alerta, "detalhe": self.detalhe or self.alerta,
                    "ultima_rodada": self.ultima_rodada, "proxima_em": self.proxima_em, "reinicio_pendente": self.reiniciar,
                    "log": list(self.eventos[-12:])}

    def bater(self) -> None:
        d = self.dados()
        try:
            _escrever(self.saida / "status.json", d)
            if self.drive and self.drive.exists():     # painel "Agentes" do dashboard (mesmo formato do agente do SIOPI)
                _escrever(self.drive / f"agente_status_{AGENTE}.json", d)
        except OSError:
            pass                                      # Drive sincronizando: tenta de novo no próximo batimento

    def iniciar(self) -> None:
        self.bater()
        def laco():
            while not self._parar_thread.wait(self.intervalo_s):
                try:
                    self.bater()
                except Exception:          # o batimento nunca pode morrer em silêncio
                    pass
        self._thread = threading.Thread(target=laco, daemon=True)
        self._thread.start()

    def encerrar(self) -> None:
        self._parar_thread.set()
        with self._lock:
            self.estado, self.detalhe = "desligado", ""
        self.bater()

    # ----- comandos (do painel do Windows e do dashboard) -----
    def comandos(self) -> List[str]:
        achados = []
        pastas = [(self.saida, "comando_*.json")]
        if self.drive and self.drive.exists():
            pastas.append((self.drive, f"agente_comando_{AGENTE}_*.json"))
        for pasta, padrao in pastas:
            for arq in sorted(pasta.glob(padrao)):
                try:
                    cmd = json.loads(arq.read_text(encoding="utf-8")).get("comando")
                except (ValueError, OSError):
                    continue
                try:
                    arq.unlink()
                except OSError:
                    pass
                if cmd in COMANDOS:
                    achados.append(cmd)
        return achados

    def processar_comandos(self) -> List[str]:
        feitos = self.comandos()
        for c in feitos:
            if c == "pausar":
                self.pausado = True
            elif c == "retomar":
                self.pausado = False
                self.acordar.set()
            elif c == "limpar_alerta":
                self.alerta = ""
            elif c in ("reiniciar", "forcar_reinicio"):
                self.reiniciar = True
            elif c == "rodar_agora":
                self.acordar.set()
            elif c == "parar":
                self.parar = True
            self.evento(f"comando: {c}")
        if feitos:
            self.bater()
        return feitos


class NotificadorRegistro(Notificador):
    """Repassa cada aviso ao iPhone e o registra no painel."""
    def __init__(self, destino: Notificador, status: Status):
        self.destino, self.status = destino, status

    def enviar(self, titulo, texto, prioridade="default", anexo=None):
        self.status.evento(titulo)
        self.destino.enviar(titulo, texto, prioridade, anexo)


# ---------- usado pela janela do Windows (sem interface, para poder testar) ----------
def ler_status(saida="saida") -> Optional[dict]:
    try:
        return json.loads((Path(saida) / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def resumo_painel(d: Optional[dict], agora: Optional[datetime] = None) -> dict:
    """Cor, título e linhas para mostrar. Offline se o batimento envelheceu."""
    agora = agora or _agora()
    if not d:
        return {"cor": "cinza", "titulo": "Sem sinal do agente", "linhas": ["O agente nunca rodou neste computador ou a pasta 'saida' não foi encontrada."], "offline": True}
    try:
        idade = (agora - datetime.fromisoformat(d["batimento_em"])).total_seconds()
    except (KeyError, ValueError):
        idade = 1e9
    if d.get("estado") == "desligado" or idade > d.get("validade_s", VALIDADE_S):
        quando = d.get("batimento_em", "?")[:16].replace("T", " ")
        return {"cor": "vermelho", "titulo": "OFFLINE", "linhas": [f"Último sinal: {quando}", "Confira se o PC está ligado, com o Windows logado, e se a tarefa AgenteEmailDanthi está ativa."], "offline": True}
    linhas = []
    if d.get("detalhe"):
        linhas.append(d["detalhe"])
    u = d.get("ultima_rodada")
    if u:
        linhas.append(f"Última rodada: {u['quando'][11:16]} · {u['emails']} e-mail(s)")
    if d.get("proxima_em"):
        linhas.append(f"Próxima rodada: {d['proxima_em'][11:16]}")
    return {"cor": d.get("cor", "verde"), "titulo": d.get("rotulo", "Online").upper(), "linhas": linhas, "offline": False}


def enviar_comando(comando: str, saida="saida") -> None:
    Path(saida).mkdir(parents=True, exist_ok=True)
    _escrever(Path(saida) / f"comando_{int(_agora().timestamp() * 1000)}_{uuid.uuid4().hex[:6]}.json", {"comando": comando})
