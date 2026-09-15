# Migração para ClassificaJá V2.18

## 1. Faça backup

Antes do primeiro deploy, faça backup do banco PostgreSQL/Supabase e do bucket de imagens.

## 2. Novas variáveis

Configure `PAYMENT_CONFIG_KEY`, `ACCOUNT_TOKEN_SECRET`, `PUBLIC_BASE_URL`, `FRONTEND_URL` e as variáveis `SMTP_*`. Para produção, mantenha `REQUIRE_EMAIL_VERIFICATION_FOR_FREE=true` e `RATE_LIMIT_ENABLED=true`.

## 3. Credenciais PagBank existentes

A V2.18 grava novas credenciais somente com `PAYMENT_CONFIG_KEY`. Para não interromper instalações V2.17.x, o backend ainda tenta ler credenciais antigas criptografadas pela derivação legada. Depois de configurar `PAYMENT_CONFIG_KEY`, abra o Painel Master e salve novamente a integração PagBank para que ela passe a usar a chave dedicada.

## 4. Banco

No primeiro startup a aplicação cria `publish_entitlements`, `product_view_events` e índices de desempenho. Registros existentes de `publish_plan_access` são copiados de forma idempotente para a nova fila de direitos de publicação.

## 5. SMTP

Sem SMTP, contas locais continuam podendo entrar, mas em produção o Plano Grátis fica bloqueado enquanto `REQUIRE_EMAIL_VERIFICATION_FOR_FREE=true` e o e-mail não estiver confirmado. Configure SMTP antes de divulgar o cadastro público.

## 6. Validação pós-deploy

Verifique `/api/health`, faça cadastro de teste, confirme o e-mail, escolha o plano grátis, publique uma imagem real, abra o anúncio e teste logout/login. Depois teste um PIX PagBank em sandbox antes de ativar produção.
