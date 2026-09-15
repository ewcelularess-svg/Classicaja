# Migração ClassificaJá V2.18.9

## Correção do fluxo de publicação com plano ativo

Esta versão corrige o comportamento do botão **Anunciar** para contas que já possuem plano válido e vagas disponíveis.

### Antes
Os botões **Anunciar** do cabeçalho e da navegação mobile enviavam sempre para `/escolher-plano`, fazendo o usuário passar pela tela de plano mesmo com Plus/Premium ativo.

### Agora
- Usuário autenticado toca em **Anunciar** -> vai para `/publicar`.
- A rota `/publicar` consulta `/api/me/publish-plan`.
- Se `ready=true`, abre diretamente o formulário de publicação.
- Se não houver plano válido, o plano estiver vencido ou o limite estiver cheio, o sistema redireciona automaticamente para `/escolher-plano`.
- Usuário não autenticado continua sendo enviado para `/entrar`.

Não há migração de banco e não são necessárias novas variáveis no Railway.
