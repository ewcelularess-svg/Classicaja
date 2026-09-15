# ClassificaJá V2.18.0

Marketplace/classificados com frontend React/Vite e backend FastAPI. A V2.18 é uma versão de segurança e estabilidade construída sobre a V2.17.5, preservando o visual atual.

## Stack

- Frontend: React 18 + Vite + React Router + Lucide
- Backend: FastAPI + Python
- Banco local: SQLite
- Produção: PostgreSQL/Supabase
- Imagens: Supabase Storage ou pasta local
- Pagamentos: PIX PagBank
- Login: e-mail/senha, Google e Facebook

## Melhorias V2.18

A versão corrige incompatibilidade SQLite/PostgreSQL no chat, impede uploads órfãos durante publicação inválida, valida/reprocessa imagens reais, adiciona logout com revogação de sessão, hash de tokens novos, recuperação de senha, confirmação de e-mail, rate limiting, validação real de CPF/CNPJ, fila de direitos de publicação para múltiplas compras, índices de banco, redução do N+1 do catálogo e deduplicação de visualizações.

## Executar localmente

Backend:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Frontend, em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`  
API/docs: `http://localhost:8000/docs`

## Produção

O `Dockerfile` compila o frontend e serve frontend + API no mesmo serviço. Use `render.yaml` como base e configure as variáveis descritas em `.env.example` / `VARIAVEIS_RENDER.txt`.

Variáveis particularmente importantes na V2.18:

- `PAYMENT_CONFIG_KEY`: chave exclusiva para criptografar credenciais de pagamento novas.
- `ACCOUNT_TOKEN_SECRET`: assinatura dos links de confirmação/redefinição.
- `PUBLIC_BASE_URL` e `FRONTEND_URL`: domínio público.
- `SMTP_*`: confirmação de e-mail e recuperação de senha.
- `REQUIRE_EMAIL_VERIFICATION_FOR_FREE=true`: reduz abuso do plano grátis.
- `RATE_LIMIT_ENABLED=true`: proteção básica contra automação abusiva.

## Migração

A inicialização continua compatível com bancos das versões anteriores. A V2.18 cria automaticamente novas tabelas/índices e migra o acesso de publicação legado para a fila de `publish_entitlements` sem apagar a tabela antiga.

Leia também `LEIA-ME_V2_18.txt` e `MIGRACAO_V2_18.md`.
