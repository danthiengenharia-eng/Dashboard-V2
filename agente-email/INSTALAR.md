# Instalar o agente no PC (Windows) ou no Mac Mini

Pré-requisitos: Python 3.11+, Drive para desktop (com a pasta `Laudos` visível), conta de serviço do Google
(veja docs/CONTA_DE_SERVICO.md) e o app **ntfy** no iPhone.

1. Baixe esta pasta (`agente-email/`) para o computador, por exemplo `C:\agente\agente-email`.
2. No terminal da pasta:  `pip install -r requirements.txt`
3. Copie `.env.exemplo` para `.env` e preencha (senha do e-mail, caminhos, tópico do ntfy).
   Copie `config.exemplo.json` para `config.json` (pastas do e-mail e regra de revisão).
4. **Aviso no iPhone:** instale o app ntfy, toque em "+" e assine o mesmo tópico escrito em `NTFY_TOPICO`
   (use um nome longo e difícil de adivinhar, ele é a "senha" do canal).
5. **Teste sem risco primeiro:** faça uma cópia da planilha, compartilhe com a conta de serviço e aponte
   o `CONFIG_DASHBOARD` para uma cópia do arquivo de configuração com o `sid` da planilha de teste.
   Rode `python -m agente_email --uma-vez` e confira a linha criada, as pastas e o aviso.
6. **Rodar sempre:** `python -m agente_email --loop` (a cada 5 minutos).
   No Windows, para iniciar sozinho com o computador (Agendador de Tarefas):
   `schtasks /Create /SC ONSTART /TN "AgenteEmailDanthi" /TR "cmd /c cd /d C:\agente\agente-email && python -m agente_email --loop" /RU SYSTEM`
   No Mac Mini: um `launchd` com o mesmo comando (posso escrever o arquivo quando o equipamento chegar).

Registros em `saida/agente.log`; memória do que já foi feito em `saida/estado.json` (não apagar).
Se o agente não conseguir fazer algo, ele não altera nada e avisa no celular.
