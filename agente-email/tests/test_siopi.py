import base64
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agente_email.agente import rodar_uma_vez
from agente_email.siopi import SiopiArquivos, campos_planilha, tipologia_siopi
from tests.test_fluxo import HOJE, OS, OSP, TXT as TXT_BASE, Mensagem, convocacao, montar

RESULTADO = {"endereco": "RUA FELIPE DOS SANTOS, 5000", "bairro": "AGUA LIMPA", "cep": "27250-390", "area_privativa": "57,04",
             "municipio": "CIDADE EXEMPLO", "atividade_extraida": "A413", "tipo_construcao": "Casa", "complemento": "APTO 302",
             "matricula": "42607", "cnm": "0123", "valor_compra_venda": "250.000,00", "categoria": "Usado", "data_abertura": "26/11/2026",
             "documentos": [{"nome": "matricula.pdf", "bytes": base64.b64encode(b"PDF1").decode(), "mimeType": "application/pdf"},
                            {"nome": "falhou.pdf"}]}


class Relogio:
    """Tempo simulado: dormir() avança o relógio e, se houver `ao_dormir`, simula o agente do SIOPI."""
    def __init__(self):
        self.t, self.chamadas, self.ao_dormir = 0.0, 0, None

    def agora(self):
        return self.t

    def dormir(self, seg):
        self.chamadas += 1
        self.t += seg
        if self.ao_dormir:
            self.ao_dormir()


def com_siopi(tmp_path, mensagens):
    ctx, caixa, plan, notif = montar(tmp_path, mensagens)
    rel = Relogio()
    ctx.siopi = SiopiArquivos(tmp_path / "Laudos", dormir=rel.dormir, relogio=rel.agora)
    ctx.rel = rel
    ctx.relogio = datetime(2026, 11, 28, 10, 0)
    ctx.agora = lambda: ctx.relogio
    return ctx, caixa, plan, notif


def responder(raiz, pid, resultado, estado="pronto"):
    (raiz / f"siopi_resposta_{pid}.json").write_text(json.dumps({"id": pid, "estado": estado, "resultado": resultado}), encoding="utf-8")


def pedido_pendente(raiz):
    return json.loads(next(raiz.glob("siopi_pedido_*.json")).read_text(encoding="utf-8"))


def agente_responde(raiz, resultado=RESULTADO, vezes=None):
    """Simula o agente do SIOPI: responde a cada pedido que aparecer."""
    def f():
        for arq in list(raiz.glob("siopi_pedido_*.json")):
            ped = json.loads(arq.read_text(encoding="utf-8"))
            if not (raiz / f"siopi_resposta_{ped['id']}.json").exists():
                responder(raiz, ped["id"], resultado)
    return f


def test_tipologia_complemento_prevalece_sobre_construcao():
    t, aviso = tipologia_siopi({"tipo_construcao": "Casa", "complemento": "APTO 302"}, ["Apartamento", "Casa"])
    assert t == "Apartamento" and "complemento" in aviso
    assert tipologia_siopi({"tipo_construcao": "Casa"}, ["Apartamento", "Casa"]) == ("Casa", "")


def test_os_so_entra_na_planilha_completa(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    ctx.rel.ao_dormir = agente_responde(raiz)
    pasta = raiz / "2026-11" / "S1-A413-1111222200000000120260101"
    original = plan.adicionar

    def conferindo(campos):                   # no instante da inserção, o resto já precisa estar pronto
        assert (pasta / "02 - Documentos" / "matricula.pdf").read_bytes() == b"PDF1"
        assert campos["matricula"] == "42607" and campos["categoria"] == "Usado"
        return original(campos)
    plan.adicionar = conferindo
    rodar_uma_vez(ctx)                        # UMA rodada basta
    l = plan.listar()[0]
    assert (l["matricula"], l["cnm"], l["vcv"], l["categoria"], l["abr"]) == ("42607", "0123", "R$ 250.000,00", "Usado", "26/11/2026")
    assert (l["end"], l["bairro"], l["area"], l["tip"]) == ("Rua Felipe dos Santos, 5000", "Agua Limpa", "57,04 m²", "Apartamento")
    assert caixa.movidas == {"1": "Ordem de Serviço"} and not list(raiz.glob("siopi_*.json"))
    assert len(notif.enviados) == 1 and "SIOPI: Usado · Apartamento · matrícula 42607 · 1 documento(s) salvos (1 não baixaram)" in notif.enviados[0]["texto"]


def test_varias_os_uma_de_cada_vez_cada_uma_completa(tmp_path):
    def conv(os_num, mid):
        t = TXT_BASE.replace(OS, os_num)
        return Mensagem("AG1@CAIXA.GOV.BR", f"Convocação de Ordem da Serviço {os_num}", t, [("c.txt", t.encode())], id=mid, bruto=b"E")
    OS_B = "5555.6666.000000002/2026.01.01"
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", conv(OS, "<1>")), ("2", conv(OS_B, "<2>"))])
    raiz = tmp_path / "Laudos"
    ctx.rel.ao_dormir = agente_responde(raiz)
    rodar_uma_vez(ctx)
    linhas = plan.listar()
    assert [l["item"] for l in linhas] == ["1", "2"] and all(l["matricula"] == "42607" for l in linhas)
    assert len(notif.enviados) == 2


def test_siopi_offline_nao_cria_os_pela_metade(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    rodar_uma_vez(ctx)                                  # ninguém responde
    assert plan.listar() == [] and caixa.movidas == {} and not list(raiz.glob("siopi_pedido_*.json"))
    assert not (raiz / "2026-11").exists()              # nem pastas nem linha
    assert "SIOPI sem resposta" in notif.enviados[0]["titulo"] and "NÃO foi criada" in notif.enviados[0]["texto"]


def test_apos_tres_tentativas_cria_sem_siopi_e_completa_depois(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    rodar_uma_vez(ctx); rodar_uma_vez(ctx)
    assert plan.listar() == []
    rodar_uma_vez(ctx)                                  # 3ª tentativa: cria sem SIOPI para não perder a demanda
    l = plan.listar()[0]
    assert l["matricula"] == "" and caixa.movidas == {"1": "Ordem de Serviço"}
    assert "SEM os dados do SIOPI" in notif.enviados[-1]["texto"]
    ctx.rel.ao_dormir = None
    ped = pedido_pendente(raiz)                          # a rodada já deixou um pedido para completar depois
    responder(raiz, ped["id"], RESULTADO)
    rodar_uma_vez(ctx)
    assert plan.listar()[0]["matricula"] == "42607"


def test_sem_siopi_obrigatorio_nunca_cria_incompleta(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    ctx.permitir_sem_siopi = False
    for _ in range(5):
        rodar_uma_vez(ctx)
    assert plan.listar() == [] and caixa.movidas == {}


def test_segunda_os_com_siopi_fora_nao_espera_de_novo(tmp_path):
    OS_B = "5555.6666.000000002/2026.01.01"
    t2 = TXT_BASE.replace(OS, OS_B)
    m2 = Mensagem("AG1@CAIXA.GOV.BR", f"Convocação de Ordem da Serviço {OS_B}", t2, [("c.txt", t2.encode())], id="<2>")
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao()), ("2", m2)])
    rodar_uma_vez(ctx)
    assert ctx.rel.t <= 100                             # esperou ~90 s uma vez, não 90 s por e-mail


def test_resposta_ainda_sincronizando_nao_quebra(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    estados = iter(["parcial", "completo"])

    def f():
        ped = json.loads(next(raiz.glob("siopi_pedido_*.json")).read_text(encoding="utf-8"))
        if next(estados, "completo") == "parcial":
            (raiz / f"siopi_resposta_{ped['id']}.json").write_text("{ incompleto", encoding="utf-8")
        else:
            responder(raiz, ped["id"], RESULTADO)
    ctx.rel.ao_dormir = f
    rodar_uma_vez(ctx)
    assert plan.listar()[0]["matricula"] == "42607"


def test_nao_repete_nem_duplica_documentos(tmp_path):
    ctx, caixa, plan, notif = com_siopi(tmp_path, [("1", convocacao())])
    raiz = tmp_path / "Laudos"
    ctx.rel.ao_dormir = agente_responde(raiz)
    rodar_uma_vez(ctx)
    n = len(notif.enviados)
    for _ in range(3):
        rodar_uma_vez(ctx)
    assert len(notif.enviados) == n and len(plan.listar()) == 1
    docs = list((raiz / "2026-11" / "S1-A413-1111222200000000120260101" / "02 - Documentos").iterdir())
    assert len(docs) == 1


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
