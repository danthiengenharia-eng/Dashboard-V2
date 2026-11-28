import base64
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.agente import rodar_uma_vez
from agente_email.siopi import SiopiArquivos, campos_planilha, tipologia_siopi
from tests.test_fluxo import HOJE, OS, OSP, convocacao, montar

RESULTADO = {"endereco": "RUA FELIPE DOS SANTOS, 5000", "bairro": "AGUA LIMPA", "cep": "27250-390", "area_privativa": "57,04",
             "municipio": "CIDADE EXEMPLO", "atividade_extraida": "A413", "tipo_construcao": "Casa", "complemento": "APTO 302",
             "matricula": "42607", "cnm": "0123", "valor_compra_venda": "250.000,00", "categoria": "Usado", "data_abertura": "26/11/2026",
             "documentos": [{"nome": "matricula.pdf", "bytes": base64.b64encode(b"PDF1").decode(), "mimeType": "application/pdf"},
                            {"nome": "falhou.pdf"}]}


def com_siopi(tmp_path, mensagens):
    ctx, caixa, plan, notif = montar(tmp_path, mensagens)
    ctx.siopi = SiopiArquivos(tmp_path / "Laudos")
    ctx.relogio = datetime(2026, 11, 28, 10, 0)
    ctx.agora = lambda: ctx.relogio
    return ctx, caixa, plan, notif


def responder(raiz, pid, resultado, estado="pronto"):
    (raiz / f"siopi_resposta_{pid}.json").write_text(json.dumps({"id": pid, "estado": estado, "resultado": resultado}), encoding="utf-8")


def pedido_pendente(raiz):
    return json.loads(next(raiz.glob("siopi_pedido_*.json")).read_text(encoding="utf-8"))


def test_tipologia_complemento_prevalece_sobre_construcao():
    t, aviso = tipologia_siopi({"tipo_construcao": "Casa", "complemento": "APTO 302"}, ["Apartamento", "Casa"])
    assert t == "Apartamento" and "complemento" in aviso
    assert tipologia_siopi({"tipo_construcao": "Casa"}, ["Apartamento", "Casa"]) == ("Casa", "")


def test_pedido_na_rodada_seguinte_e_dados_aplicados(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    rodar_uma_vez(ctx)                       # cria a OS e já faz o pedido ao SIOPI
    assert len(plan.listar()) == 1 and plan.listar()[0]["matricula"] == ""
    ped = pedido_pendente(raiz)
    assert ped["os"] == OS and ped["sem_imagem"] is True
    responder(raiz, ped["id"], RESULTADO)
    rodar_uma_vez(ctx)                       # lê a resposta e completa
    l = plan.listar()[0]
    assert (l["matricula"], l["cnm"], l["vcv"], l["categoria"], l["abr"]) == ("42607", "0123", "R$ 250.000,00", "Usado", "26/11/2026")
    assert (l["end"], l["bairro"], l["area"], l["tip"]) == ("Rua Felipe dos Santos, 5000", "Agua Limpa", "57,04 m²", "Apartamento")
    pasta = tmp_path / "Laudos" / "2026-11" / "S1-A413-1111222200000000120260101"
    assert (pasta / "02 - Documentos" / "matricula.pdf").read_bytes() == b"PDF1"
    assert not list(raiz.glob("siopi_*.json"))                       # arquivos temporários removidos
    assert "completada pelo SIOPI" in notif.enviados[-1]["titulo"] and "1 documento" in notif.enviados[-1]["texto"]
    assert "1 documento(s) do SIOPI não baixaram" in notif.enviados[-1]["texto"]


def test_nao_repete_nem_duplica_documentos(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    rodar_uma_vez(ctx)
    responder(raiz, pedido_pendente(raiz)["id"], RESULTADO)
    rodar_uma_vez(ctx)
    n = len(notif.enviados)
    for _ in range(3):
        rodar_uma_vez(ctx)
    assert len(notif.enviados) == n and not list(raiz.glob("siopi_pedido_*.json"))
    docs = list((raiz / "2026-11" / "S1-A413-1111222200000000120260101" / "02 - Documentos").iterdir())
    assert len(docs) == 1


def test_agente_do_siopi_offline_tenta_de_novo_e_depois_desiste(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    rodar_uma_vez(ctx)                                  # pedido 1, ninguém responde
    ids = {pedido_pendente(raiz)["id"]}
    for _ in range(3):
        ctx.relogio += timedelta(minutes=4)             # passou dos 3 min sem resposta
        rodar_uma_vez(ctx)                              # descarta o pedido
        rodar_uma_vez(ctx)                              # refaz (na 3ª vez desiste)
        if list(raiz.glob("siopi_pedido_*.json")):
            ids.add(pedido_pendente(raiz)["id"])
    assert len(ids) == 3                                # três tentativas, pedidos diferentes
    assert not list(raiz.glob("siopi_pedido_*.json"))   # desistiu: nada fica esperando
    assert sum("SIOPI não respondeu" in n["titulo"] for n in notif.enviados) == 1
    assert len(plan.listar()) == 1 and plan.listar()[0]["matricula"] == ""   # a OS criada não foi afetada


def test_resposta_ainda_sincronizando_nao_quebra(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    rodar_uma_vez(ctx)
    pid = pedido_pendente(raiz)["id"]
    (raiz / f"siopi_resposta_{pid}.json").write_text("{ incompleto", encoding="utf-8")
    rodar_uma_vez(ctx)
    assert plan.listar()[0]["matricula"] == ""
    responder(raiz, pid, RESULTADO)
    rodar_uma_vez(ctx)
    assert plan.listar()[0]["matricula"] == "42607"


def test_municipio_diferente_no_siopi_so_avisa(tmp_path):
    novos, avisos = campos_planilha({"municipio": "OUTRA CIDADE"}, {"mun": "Cidade Exemplo (Deslocamento especial)", "atv": "A413"})
    assert "mun" not in novos and any("difere" in a for a in avisos)


def test_reiniciar_pendentes_volta_so_o_que_nao_terminou(tmp_path):
    from agente_email.estado import Estado
    from agente_email.siopi import reiniciar_pendentes
    e = Estado()
    e.set("siopi:A", etapa="desistiu", tentativas=3, pedido="x")
    e.set("siopi:B", etapa="aguardando", pedido="y", enviado="2026-11-28T10:00:00")
    e.set("siopi:C", etapa="completo")
    e.set("<mensagem>", etapa="completo")
    assert reiniciar_pendentes(e) == 2
    assert e.get("siopi:A")["etapa"] == "pendente" and e.get("siopi:A")["tentativas"] == 0
    assert e.get("siopi:C")["etapa"] == "completo" and e.get("<mensagem>")["etapa"] == "completo"
