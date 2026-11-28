# Contexto do projeto (decisões já tomadas)

Resumo da conversa de planejamento, para qualquer sessão ou pessoa retomar sem perder o fio.

## Objetivo
Automatizar o ciclo das demandas da CEF: ler e-mails, atualizar o dashboard, conferir com o SIOPI,
preencher o SIMIL e, depois, gerar modelos SisDEA. O dashboard (index.html) será reformulado por último.

## Arquitetura
- Dashboard = planilha Google (1 linha por OS) + pastas no Drive (`Laudos/<mês>/<item>-<OS>`, 4 subpastas).
- Agentes rodam em máquina local sempre ligada (hoje o PC Windows; depois um Mac Mini) e conversam com o
  dashboard por arquivos/planilha. O PC do SIMIL/SisDEA fica em `D:\Gerador de modelo sisDEA`.
- SIMIL já funciona assim: dashboard grava `simil_pedido_*.json` na pasta da OS, o agente local executa e
  grava `simil_status.json`. O SisDEA seguirá o mesmo modelo (`sisdea_pedido_*.json`).
- Configuração do dashboard (atividades, municípios, polos, colunas) hoje fica no localStorage do navegador:
  precisa ser exportada para o agente.

## Agente de e-mail (a cada 5 minutos, IMAP da Hostgator, usuário e senha)
| E-mail | Assunto | Ação | Pasta IMAP |
|---|---|---|---|
| Nova demanda | `Convocação de Ordem da Serviço <OS>` (+ .txt) | cria OS, pastas, sobe o .txt | Ordem de Serviço |
| Conclusão | `Conclusão da Ordem de Serviço <OS>` | status Concluída; confere valores efetivos | Conclusão OS |
| Cancelamento | `Cancelamento da Ordem Serviço <OS>` | status Cancelada (avisa se já havia serviço feito) | Cancelamento OS |
| Revisão | `Solicitação de revisão do valor de avaliação` (OS só no corpo) | status "Em revisão", prazo 6 dias corridos | A DEFINIR (sugestão: Revisão OS) |
| PEPT | `Resolução do PEPT da OS` (OS só no corpo) | sinaliza resposta da PEPT | Pendências PEPT |

- O e-mail só é movido depois de confirmar que a planilha e as pastas foram atualizadas.
- Remetente varia (cada agência/unidade tem a sua caixa, ou correspondente bancário): aceitar qualquer
  `@caixa.gov.br` e classificar pelo assunto. O que vale é o conteúdo do e-mail e do anexo.
- Qualquer dúvida (tipo, OS ausente ou divergente): não altera nada e avisa.
- Acentos chegam corrompidos em alguns e-mails (mojibake): tratado em `agente_email/texto.py`.

## Conferência com o SIOPI
Todo dia às 23:55: o agente que já busca no SIOPI compara as demandas de lá com a planilha e gera relatório
de divergências (sem corrigir sozinho). Login por usuário e senha; sessão ~1 h; se o site estiver fora,
3 tentativas com 10 min de intervalo e depois repete de manhã.

## Notificações e app
iPhone: aviso via ntfy (ou Telegram) e evento no Google Agenda/Calendário. PWA instalável só depois da
reformulação visual.

## Deslocamento especial
O agente compara o valor de deslocamento do .txt (e do SIOPI, quando houver) com a configuração do município:
igual ao padrão = Não; igual a 21% do padrão (ex.: 40,00 -> 8,40) = Sim; qualquer outro valor ou fontes divergentes =
Indefinido (não decide, avisa). Quando Sim, o município é gravado como "<Município> (Deslocamento especial)", igual ao dashboard.

## Google
- Conta de serviço criada (projeto `agente-danthi`): agente-email@agente-danthi.iam.gserviceaccount.com — só enxerga a planilha das OS.
- A chave JSON fica só no computador do agente (fora do Drive e do git). Pastas/arquivos usam o Drive para desktop.
- A configuração do dashboard está no Drive em `dashboard-cef-config.json` (IDs, colunas, atividades, municípios).
- Objetivo de longo prazo: depender menos do Google; por isso o acesso à planilha fica atrás de `planilha.py`.

## Estado
- Pronto: classificador, leitor da convocação, valores da conclusão, regras de conclusão/cancelamento/revisão/PEPT sobre a planilha (`acoes.py`, `planilha.py`), 39 testes (`python -m pytest tests`).
- Pronto também: criação da OS a partir da convocação (item = maior item + 1; mês = mês atual; entrega = entrada + prazo da atividade; valores pelas tabelas; deslocamento especial detectado), conferida com a configuração real (`dashboard-cef-config.json`).
- Próximo: criar as pastas/subpastas e salvar anexos pelo Drive para desktop, leitura do IMAP da Hostgator, notificação no iPhone, conferência SIOPI das 23:55.
- Precisa do usuário: exportar a configuração do dashboard; pasta de destino da revisão; código do agente
  do SIOPI (que está no PC); conta de serviço do Google.
- Mac Mini ainda não comprado: tudo roda no Windows por enquanto.
