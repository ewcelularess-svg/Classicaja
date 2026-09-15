# Validação V2.18.12

Validações executadas nesta hotfix:

- `backend/main.py` compilado com `python -m py_compile`.
- `frontend/package.json` validado como JSON.
- Verificação estática da ordem dos hooks no componente `Admin`.
- Confirmado que não existem hooks React após os retornos condicionais iniciais do Painel Master.
- Confirmado que os atalhos funcionais adicionados na V2.18.11 foram preservados.

## Teste após deploy

1. Abra `/api/health` e confirme `version: 2.18.12`.
2. Abra `/admin` e aguarde a carga completa.
3. Teste os cards: Contas, Anúncios, Visualizações, Destaques ativos, Receita, Atendimentos e Denúncias.
4. Abra o painel do usuário e teste os cards de métricas.
