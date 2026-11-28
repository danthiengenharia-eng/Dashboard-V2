# Conta de serviço do Google (acesso do agente só à planilha)

Faz-se uma única vez, no PC, logado na conta Google dona da planilha. Não tem custo.

1. Abra https://console.cloud.google.com e crie um projeto (menu superior → *Novo projeto*), nome: `agente-danthi`.
2. Menu → *APIs e serviços* → *Biblioteca* → procure **Google Sheets API** → *Ativar*.
   (A API do Drive não é necessária: pastas e arquivos usam o Drive para desktop.)
3. Menu → *IAM e administrador* → *Contas de serviço* → *Criar conta de serviço*.
   Nome: `agente-email`. Pule as etapas de papéis e de acesso de usuários → *Concluir*.
4. Clique na conta criada → aba *Chaves* → *Adicionar chave* → *Criar nova chave* → **JSON** → *Criar*.
   O arquivo é baixado. **Ele é como uma senha.**
5. Mova o arquivo para uma pasta fora do Drive e fora do repositório, ex.: `C:\agente\google-sa.json`.
   Nunca envie o conteúdo por chat, e-mail ou GitHub.
6. Copie o e-mail da conta de serviço (algo como `agente-email@agente-danthi.iam.gserviceaccount.com`).
7. Abra a planilha das OS → *Compartilhar* → cole esse e-mail → permissão **Editor** →
   desmarque "Notificar pessoas" → *Compartilhar*. Compartilhe só a planilha.
8. Informe ao desenvolvedor apenas o e-mail da conta de serviço (não a chave).

Se a criação de chave estiver bloqueada (política da organização), avise: há alternativa.
Para desligar o acesso a qualquer momento: remova o compartilhamento da planilha ou exclua a chave.
