# Validação técnica — ClassificaJá V2.18.10

- Backend Python compilado com `py_compile` sem erros.
- Inicialização local da nova tabela `support_requests` validada em SQLite.
- Envio de solicitação de suporte testado e persistido com status `open` e protocolo.
- Nova rota de atendimento conectada ao frontend.
- Painel Master recebe `/api/admin/support-requests` e ação de resolver.
- Rate limit aplicado ao endpoint público de atendimento.
- Rodapé responsivo e botão voltar ao topo adicionados sem alterar as rotas de publicação/pagamentos.

Observação: a instalação npm no ambiente de validação excedeu o tempo disponível; a validação frontend foi feita por inspeção estrutural dos componentes/rotas e preservação das dependências já existentes do projeto.
