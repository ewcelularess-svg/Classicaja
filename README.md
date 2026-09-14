# ClassificaJá V2.2 — Render + Supabase

Marketplace responsivo para notebook e celular, preparado para iniciar em hospedagem gratuita.

## Arquitetura de produção

- **Frontend:** React + Vite
- **Backend:** FastAPI
- **Banco:** PostgreSQL do Supabase
- **Fotos:** Supabase Storage
- **Hospedagem:** Render Web Service em Docker
- **Modo local:** SQLite + pasta `backend/uploads`

No Render, um Dockerfile multiestágio compila o React e inicia o FastAPI, que também serve o build do React. Isso permite publicar frontend e backend em **um único serviço**, usando a mesma URL e evitando configuração de CORS entre dois domínios.

## Recursos presentes

- Cadastro e login
- Publicação, edição e exclusão de anúncios
- Categorias, cidade e bairro
- Fotos de produtos
- Busca, filtros e ordenação
- Favoritos
- WhatsApp
- Chat interno
- Painel do vendedor e métricas
- Denúncias e moderação
- Vendedores verificados
- Anúncios destacados
- Fluxo de pagamento demonstrativo para PIX/cartão
- Painel administrativo
- Interface responsiva para celular, tablet e notebook

## Teste local rápido

### Backend

No Windows, abra a pasta `backend` e execute `iniciar_backend.bat`.

Ou pelo terminal:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

API: http://localhost:8000
Docs: http://localhost:8000/docs

Sem `DATABASE_URL`, o projeto usa SQLite automaticamente.

### Frontend

Em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

Site: http://localhost:5173

## Produção grátis

Leia **DEPLOY_GRATIS_RENDER_SUPABASE.md**. O arquivo `render.yaml` já está pronto.

## Segurança

Nunca coloque `SUPABASE_SECRET_KEY`, senha do banco ou senha do administrador no frontend ou em um repositório público. Configure esses valores apenas nas variáveis secretas do Render.
