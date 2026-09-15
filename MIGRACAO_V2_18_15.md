# Migração V2.18.15

## Objetivo
Adicionar retenção e reativação por Web Push sem alterar as regras dos planos.

## Banco
A inicialização cria/ajusta automaticamente:

- `users.last_seen_at`
- `favorites.created_at`
- `notifications.action_url`
- preferências individuais em `push_preferences`
- tabela `retention_events` para idempotência e controle de frequência

Não é necessária migração manual no PostgreSQL/Supabase.

## Alertas

- Mensagens: imediato.
- Favoritos: imediato.
- Desempenho: quando houver atividade nas últimas 24h.
- Vencimento: 7, 3 e 1 dia antes.
- Expiração: aviso após o vencimento recente.
- Inatividade: após 7 dias sem entrar, no máximo semanal.
- Resumo semanal: visualizações, favoritos e anúncios.

Lembretes programados respeitam um limite de um por usuário a cada 24 horas, priorizando vencimento/expiração, retorno, desempenho e resumo semanal.

## Railway
Nenhuma nova variável é obrigatória. O comportamento pode ser ajustado opcionalmente com `RETENTION_ENABLED` e `RETENTION_LOOP_SECONDS`.
