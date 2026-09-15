# Validação V2.18.15

- Backend Python compilado com sucesso (`py_compile`).
- Migração SQLite validada com criação das novas colunas e `retention_events`.
- API de preferências push validada com todos os toggles individuais.
- Favorito validado: gera notificação direcionada ao vendedor com `action_url`.
- Ciclo de retenção validado com lembrete de inatividade e idempotência em execução repetida.
- Cadência validada: no máximo um lembrete automático por usuário em 24 horas.
- Service Worker atualizado para ação genérica “Abrir no ClassificaJá”.
- Health esperado: `2.18.15`.

Observação: o build Vite não foi executado neste ambiente porque as dependências npm não estavam disponíveis localmente; a estrutura JSX/CSS alterada foi revisada e mantida sobre a base já funcional da V2.18.14.
