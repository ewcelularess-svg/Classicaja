# Validação técnica — ClassificaJá V2.18.0

## Testes executados

- Importação/compilação do backend Python: OK.
- Inicialização limpa do SQLite e migrações: OK.
- Cadastro e login: OK.
- Senha mínima e telefone inválido: bloqueados.
- Sessão nova armazenada como SHA-256: OK.
- Migração de sessão legada em texto puro para SHA-256: OK, mantendo o bearer do cliente válido.
- Confirmação de e-mail por token assinado: OK.
- Logout com revogação no servidor: OK.
- Troca de senha revogando outras sessões: OK.
- Redefinição de senha e invalidação do link após uso: OK.
- Publicação sem plano: bloqueada antes de gravar imagem.
- Arquivo falso renomeado para `.jpg`: rejeitado.
- JPG real: validado/reprocessado/publicado.
- Galeria com lote parcialmente inválido: rollback dos novos uploads e anúncio preservado.
- Busca sem diferença entre maiúsculas/minúsculas: OK.
- Catálogo em lote sem telefone do vendedor: OK; telefone permanece no detalhe.
- Deduplicação de visualização por visitante/produto/hora: OK.
- Dois direitos de publicação simultâneos: preservados sem sobrescrita.
- CPF e CNPJ válidos: aceitos; CPF repetitivo inválido: rejeitado.
- Ocultar conversa duas vezes: OK com UPSERT portável.
- Denúncia duplicada aberta pelo mesmo usuário/produto: bloqueada.
- Rate limit: 10 tentativas de login permitidas no teste e a 11ª recebeu HTTP 429.
- Parsing de todos os arquivos JavaScript/JSX do frontend: OK.
- `package.json`: JSON válido.
- `render.yaml`: YAML válido.

## Decisões de compatibilidade

O `styles.css` existente foi preservado para evitar regressão visual. A V2.18 adiciona somente os estilos necessários aos novos estados de autenticação/verificação.

O backend continua em `main.py` nesta versão para reduzir risco de regressão durante a rodada de segurança. A modularização em routers/services deve ser feita separadamente depois de a V2.18 estar estável em produção.

O Docker continua usando `npm install` porque o projeto de origem não possuía `package-lock.json`. Um lockfile deve ser criado e versionado em uma máquina com acesso ao registry do npm antes de migrar para `npm ci`.
