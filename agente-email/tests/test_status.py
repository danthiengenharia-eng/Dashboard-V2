import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.notificar import NotificadorMemoria
from agente_email.status import NotificadorRegistro, Status, enviar_comando, ler_status, resumo_painel

T0 = datetime(2026, 11, 28, 12, 0, tzinfo=timezone(timedelta(hours=-3)))


def novo(tmp_path, drive=True):
    d = tmp_path / "Laudos"
    d.mkdir()
    return Status(tmp_path / "saida", str(d) if drive else None, relogio=lambda: T0), d


def test_batimento_grava_arquivo_local_e_o_do_dashboard(tmp_path):
    st, drive = novo(tmp_path)
    st.bater()
    local = json.loads((tmp_path / "saida" / "status.json").read_text(encoding="utf-8"))
    no_drive = json.loads((drive / "agente_status_email.json").read_text(encoding="utf-8"))
    assert local == no_drive
    # campos que o painel "Agentes" do dashboard lê
    assert re.fullmatch(r"[a-z0-9_]+", no_drive["agente"]) and no_drive["nome"] == "Agente de e-mail"
    assert no_drive["rotulo"] == "Online" and no_drive["cor"] == "verde" and no_drive["validade_s"] == 150
    assert no_drive["batimento_em"].startswith("2026-11-28T12:00:00")


def test_estados_trabalhando_pausado_problema_e_desligado(tmp_path):
    st, _ = novo(tmp_path)
    st.estado = "trabalhando"
    assert st.dados()["rotulo"] == "Trabalhando"
    st.pausado = True
    assert (st.dados()["rotulo"], st.dados()["cor"]) == ("Pausado", "amarelo")
    st.falha("falha na rodada: OSError")
    assert (st.dados()["rotulo"], st.dados()["cor"], st.dados()["alerta"]) == ("Com problema", "vermelho", "falha na rodada: OSError")
    st.encerrar()
    assert json.loads((tmp_path / "saida" / "status.json").read_text(encoding="utf-8"))["estado"] == "desligado"


def test_comandos_do_painel_e_do_dashboard(tmp_path):
    st, drive = novo(tmp_path)
    enviar_comando("pausar", tmp_path / "saida")
    (drive / "agente_comando_email_123.json").write_text(json.dumps({"comando": "limpar_alerta"}), encoding="utf-8")
    (drive / "agente_comando_siopi_9.json").write_text(json.dumps({"comando": "pausar"}), encoding="utf-8")   # de outro agente
    (tmp_path / "saida" / "comando_x.json").write_text(json.dumps({"comando": "apagar_tudo"}), encoding="utf-8")  # desconhecido
    st.alerta = "x"
    feitos = st.processar_comandos()
    assert sorted(feitos) == ["limpar_alerta", "pausar"] and st.pausado and st.alerta == ""
    assert (drive / "agente_comando_siopi_9.json").exists()         # não mexe nos comandos dos outros
    enviar_comando("retomar", tmp_path / "saida")
    st.processar_comandos()
    assert not st.pausado and st.acordar.is_set()


def test_reiniciar_parar_e_rodar_agora(tmp_path):
    st, _ = novo(tmp_path, drive=False)
    for c in ("reiniciar", "parar", "rodar_agora"):
        enviar_comando(c, tmp_path / "saida")
    st.processar_comandos()
    assert st.reiniciar and st.parar and st.acordar.is_set()


def test_notificacoes_aparecem_no_painel(tmp_path):
    st, _ = novo(tmp_path, drive=False)
    real = NotificadorMemoria()
    NotificadorRegistro(real, st).enviar("Nova OS 1559 · Rio", "texto", "high")
    assert real.enviados[0]["prioridade"] == "high" and "Nova OS 1559 · Rio" in st.dados()["log"][-1]


def test_painel_detecta_offline_por_batimento_velho(tmp_path):
    st, _ = novo(tmp_path, drive=False)
    st.rodada_ok(3)
    st.proxima_em = "2026-11-28T12:05:00-03:00"
    st.bater()
    d = ler_status(tmp_path / "saida")
    ok = resumo_painel(d, T0 + timedelta(seconds=60))
    assert ok["titulo"] == "ONLINE" and not ok["offline"] and any("Última rodada: 12:00 · 3 e-mail(s)" in l for l in ok["linhas"])
    morto = resumo_painel(d, T0 + timedelta(minutes=10))
    assert morto["titulo"] == "OFFLINE" and morto["cor"] == "vermelho" and morto["offline"]
    assert resumo_painel(None)["offline"]


def test_batimento_nao_quebra_se_o_drive_estiver_ocupado(tmp_path):
    st, drive = novo(tmp_path)
    (drive / "agente_status_email.tmp").mkdir()          # simula bloqueio: o arquivo temporário vira pasta
    st.bater()                                           # não pode levantar exceção
    assert (tmp_path / "saida" / "status.json").exists()
