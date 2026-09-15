# Migração ClassificaJá V2.18.5

Esta versão é uma atualização visual segura sobre a V2.18.4.

## Alterações

- O título da página de detalhes deixa de usar `line-clamp: 2` no mobile e passa a ser exibido integralmente.
- Cards de anúncios exibem até 3 linhas de título.
- Quebra segura de palavras longas com `overflow-wrap`.
- Versão da API e frontend atualizada para `2.18.5`.

## GitHub + Railway

1. Substitua os arquivos do pacote de arquivos alterados mantendo as mesmas pastas.
2. Faça o commit na branch `main`.
3. Aguarde o Auto Deploy do Railway.
4. Confirme `/api/health` com `version: 2.18.5`.
5. No celular, atualize o site e abra um anúncio com título longo para validar.

Nenhuma variável nova de ambiente é necessária.
