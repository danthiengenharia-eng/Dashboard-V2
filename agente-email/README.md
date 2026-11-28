# Agente de e-mail (Danthi)

Lê a caixa de e-mail da CEF e mantém o dashboard em dia. Esta é a primeira etapa:
**reconhecimento e interpretação** dos e-mails. Ainda não acessa a caixa, o Drive nem a planilha.

| E-mail | Assunto | Ação planejada | Pasta de destino |
|---|---|---|---|
| Nova demanda | `Convocação de Ordem da Serviço <OS>` | cria a OS, as pastas e sobe o `.txt` | Ordem de Serviço |
| Conclusão | `Conclusão da Ordem de Serviço <OS>` | status Concluída; confere valores | Conclusão OS |
| Cancelamento | `Cancelamento da Ordem Serviço <OS>` | status Cancelada | Cancelamento OS |
| Revisão | `Solicitação de revisão do valor de avaliação` | status "Em revisão", prazo de 6 dias corridos | (a definir) |
| PEPT | `Resolução do PEPT da OS` | sinaliza resposta da PEPT | Pendências PEPT |

Regra de segurança: se o remetente não for `@caixa.gov.br`, o assunto não for reconhecido,
a OS não for encontrada ou divergir entre assunto e corpo, o agente **não altera nada** e avisa.

## Testar
```
pip install olefile pytest
python -m pytest tests
python scripts/validar_msg.py PASTA_COM_MSG   # valida com e-mails .msg reais (não versionar)
```
Senhas ficam em `.env` (fora do git). Exemplos reais de e-mail nunca entram no repositório.
