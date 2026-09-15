# Migração V2.18.12

## Hotfix do Painel Master

A V2.18.12 corrige uma regressão introduzida na V2.18.11 que podia deixar `/admin` em branco depois do carregamento.

### Causa
Dois hooks `useMemo()` do Painel Master eram executados somente depois do primeiro estado de carregamento. Isso fazia o React receber uma quantidade diferente de hooks entre renders e interrompia a renderização do painel.

### Correção
Os hooks de ranking de visualizações e destaques ativos agora são executados antes de qualquer retorno condicional do componente `Admin`, mantendo a ordem de hooks estável em todos os renders.

### Funcionalidades preservadas
- Cards funcionais no Painel Master.
- Ranking de visualizações.
- Lista de destaques ativos.
- Cards funcionais no painel do usuário.
- Filtros e rankings em Meus anúncios.
- Rodapé e Central de Atendimento.

### Banco e variáveis
Não há migração de banco nem variável nova de ambiente nesta versão.
