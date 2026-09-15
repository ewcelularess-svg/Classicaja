# Migração ClassificaJá V2.18.10

## O que muda

- Novo rodapé profissional do site.
- Links: Reclamações, Suporte e Sugestão.
- Nova rota pública `/atendimento` com formulário por categoria.
- Novo registro de protocolos no banco em `support_requests`.
- Nova aba `Atendimento` no Painel Master.
- Botão flutuante para voltar ao topo.

## Banco de dados

A tabela `support_requests` e seus índices são criados automaticamente no startup. Não é necessário executar SQL manualmente.

## Railway

Nenhuma variável de ambiente nova é obrigatória.

Depois do deploy, valide:

`https://www.classificaja.com.br/api/health`

Esperado: `"version":"2.18.10"`.
