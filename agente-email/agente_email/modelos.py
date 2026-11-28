from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple


@dataclass
class Mensagem:
    """E-mail já decodificado, independente da origem (IMAP ou .msg)."""
    remetente: str
    assunto: str
    corpo: str
    anexos: List[Tuple[str, bytes]] = field(default_factory=list)
    id: str = ""          # Message-ID (ou UID) para nunca processar duas vezes
    bruto: bytes = b""    # e-mail original (.eml) para arquivar na pasta da OS
    data: Optional[datetime] = None   # cabeçalho Date


@dataclass
class Classificacao:
    tipo: str                 # convocacao | conclusao | cancelamento | revisao | pept | desconhecido
    os_numero: Optional[str]  # ex.: 1111.2222.000000001/2026.01.01
    avisos: List[str] = field(default_factory=list)

    @property
    def confiavel(self) -> bool:
        """Só processa sozinho se o tipo e a OS foram identificados sem ressalvas."""
        return self.tipo != "desconhecido" and bool(self.os_numero) and not self.avisos
