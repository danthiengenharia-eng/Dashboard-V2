import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email import __versao__
from agente_email.diagnostico import gerar


def test_diagnostico_nao_vaza_senhas_e_mostra_versao(tmp_path, monkeypatch):
    saida = tmp_path / "saida"
    saida.mkdir()
    (saida / "agente.log").write_text("", encoding="utf-8")
    (saida / "estado.json").write_text('{"<a>": {"etapa": "completo"}}', encoding="utf-8")
    monkeypatch.setenv("IMAP_SENHA", "SEGREDO-123")
    monkeypatch.setenv("ICLOUD_SENHA", "OUTRO-SEGREDO")
    monkeypatch.setenv("PASTA_LAUDOS", str(tmp_path))
    texto = gerar(saida)
    assert __versao__ in texto and "agente.log está VAZIO" in texto and "{'completo': 1}" in texto
    assert "SEGREDO-123" not in texto and "OUTRO-SEGREDO" not in texto
    assert "IMAP_SENHA: preenchido" in texto


def test_inicia_como_os_outros_agentes_com_raiz():
    import subprocess
    raiz = os.path.join(os.path.dirname(__file__), "..")
    r = subprocess.run([sys.executable, "-m", "agente_email.agente", "--help"], cwd=raiz, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "--raiz" in r.stdout and "--loop" in r.stdout
