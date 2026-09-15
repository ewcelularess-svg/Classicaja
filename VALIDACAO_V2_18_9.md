# Validação técnica — ClassificaJá V2.18.9

- Botão **Anunciar** do cabeçalho aponta para `/publicar` quando autenticado.
- Botão **Anunciar** da barra inferior aponta para `/publicar` quando autenticado.
- `PublishGate` continua responsável por validar plano e cota antes de renderizar o formulário.
- Sem plano / plano vencido / cota cheia continuam redirecionando para `/escolher-plano`.
- Usuário sem login continua redirecionando para `/entrar`.
- Versão de API atualizada para `2.18.9`.
