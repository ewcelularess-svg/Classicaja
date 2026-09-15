# Migração V2.18.13

## Objetivo
Adicionar notificações push de novos anúncios com opt-in do usuário, filtros e envio de teste.

## Alterações
- nova dependência backend: `pywebpush>=2,<3`;
- novo Service Worker: `frontend/public/push-sw.js`;
- tabelas `app_settings`, `push_preferences` e `push_subscriptions`;
- geração persistente automática de chaves VAPID;
- endpoints para configuração, preferências, inscrição e teste de push;
- envio em background após uma publicação bem-sucedida;
- painel do usuário com aba destacada de notificações;
- filtros por cidade, categoria e somente destaques;
- CTA de notificações na visão geral do painel.

## Banco
As novas tabelas e índices são criados automaticamente no startup. Não é necessário rodar SQL manualmente.

## Railway
Nenhuma nova variável é obrigatória. As chaves VAPID são geradas e persistidas automaticamente.

## Observação
A permissão do navegador sempre depende de uma ação explícita do usuário. O site não consegue ativar notificações sem consentimento.
