"""Ensaio (sem alterar nada): descreve o que o agente faria com cada e-mail, conferindo a planilha."""
from datetime import date
from typing import List

from .acoes import preparar_os
from .classificador import classificar


def descrever(msgs, plan, cfg, hoje: date) -> List[str]:
    linhas, resumo = [], {"criar": 0, "ja_existe": 0, "aplicar": 0, "sem_os": 0, "problema": 0}
    for uid, m in msgs:
        c = classificar(m)
        quando = f"{m.data:%d/%m %H:%M}  " if m.data else "              "
        base = f"{quando}{c.tipo:13} OS {c.os_numero or '—'}"
        if c.tipo == "desconhecido":
            resumo["problema"] += 1
            assunto = " ".join((m.assunto or "").split())[:90]
            linhas.append(base + f"  | NÃO RECONHECIDO: assunto \"{assunto}\" de {m.remetente}")
            continue
        if plan is None:
            linhas.append(base + ("  | " + "; ".join(c.avisos) if c.avisos else ""))
            continue
        achadas = plan.achar_os(c.os_numero) if c.os_numero else []
        if c.tipo == "convocacao":
            if achadas:
                resumo["ja_existe"] += 1
                linhas.append(base + f"  | JÁ ESTÁ NA PLANILHA (item {achadas[0].get('item')}): será ignorada")
                continue
            nova, avisos = preparar_os(c, m, plan, hoje, cfg)
            if nova is None:
                resumo["problema"] += 1
                linhas.append(base + "  | NÃO SERÁ CRIADA: " + "; ".join(avisos))
            else:
                resumo["criar"] += 1
                k = nova.campos
                linhas.append(base + f"  | CRIAR item {k['item']} · {k['atv']} · {k['mun']} · {k['tip'] or 'sem tipologia'} · "
                              f"{k['vt']} · entrega {k['ent']}" + ("  ⚠ " + "; ".join(avisos) if avisos else ""))
        else:
            if len(achadas) == 1:
                resumo["aplicar"] += 1
                linhas.append(base + f"  | APLICAR na OS item {achadas[0].get('item')} (status atual: {achadas[0].get('st')})")
            else:
                resumo["sem_os"] += 1
                linhas.append(base + ("  | OS NÃO ESTÁ NA PLANILHA: nada será alterado" if not achadas else "  | OS DUPLICADA na planilha: nada será alterado"))
    linhas.append("")
    linhas.append(f"RESUMO: {resumo['criar']} OS a criar · {resumo['ja_existe']} já existem (ignoradas) · {resumo['aplicar']} a aplicar · "
                  f"{resumo['sem_os']} sem OS na planilha · {resumo['problema']} com problema")
    return linhas
