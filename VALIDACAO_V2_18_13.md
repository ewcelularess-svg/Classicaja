# Validação V2.18.13

## Validações executadas
- `backend/main.py` compila com `py_compile`;
- OpenAPI gerado com os novos endpoints push;
- tabelas `app_settings`, `push_preferences` e `push_subscriptions` criadas em SQLite;
- par VAPID gerado com chave privada P-256 de 32 bytes e applicationServerKey pública de 65 bytes;
- leitura/gravação das preferências validada;
- todos os arquivos JS/JSX analisados sem erro de sintaxe;
- CSS analisado pelo PostCSS sem erro;
- Service Worker incluído em `frontend/public/push-sw.js`;
- health atualizado para `2.18.13`.

## Teste após deploy
1. Abra `/api/health` e confirme `version: 2.18.13`.
2. Entre em **Painel → Notificações**.
3. Toque **Ativar** e permita notificações no navegador.
4. Toque **Enviar teste**.
5. Com outra conta, publique um novo anúncio que corresponda aos filtros.
6. Confirme a notificação no Android e toque nela para abrir o anúncio.
7. Desative no painel e confirme que novos anúncios deixam de gerar push para a conta.
