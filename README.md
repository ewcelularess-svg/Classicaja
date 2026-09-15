# ClassificaJá V2.18.6

Marketplace/classificados com frontend React/Vite e backend FastAPI. A V2.18.6 mantém as correções de segurança e as regras comerciais da V2.18.2 e melhora a seleção de fotos no mobile com ações separadas para Galeria e Câmera.

## Stack

- Frontend: React 18 + Vite + React Router + Lucide
- Backend: FastAPI + Python
- Banco local: SQLite
- Produção: PostgreSQL/Supabase
- Imagens: Supabase Storage ou pasta local
- Pagamentos: PIX PagBank
- Login: e-mail/senha, Google e Facebook

## Regra de planos V2.18.2/V2.18.4

- **Grátis:** 1 anúncio, 7 dias, uso único por conta.
- **Plus:** até 5 anúncios cadastrados, validade padrão de 15 dias.
- **Premium:** até **10 anúncios cadastrados**, validade padrão de 30 dias.
- O limite considera anúncios ainda cadastrados, inclusive pausados/vendidos, pois continuam consumindo banco/storage. Excluir um anúncio libera uma vaga.
- Enquanto o plano estiver válido e houver vaga, o usuário publica sem pagar novamente.
- Plano vencido bloqueia novas publicações até renovação/upgrade permitido.
- Conta Plus pode **renovar Plus** ou **fazer upgrade para Premium**.
- Conta Premium pode **somente renovar Premium**; downgrade para Plus/Grátis é bloqueado no frontend e no backend.
- Renovação estende a validade da conta. Upgrade para Premium preserva o tempo restante e acrescenta o período Premium.
- Renovação não aumenta o teto de anúncios simultaneamente cadastrados; se a cota estiver cheia, é preciso liberar vaga. No Plus, o upgrade para Premium também pode ampliar a cota de 5 para 10.

## Melhorias herdadas da V2.18

A base inclui compatibilidade SQLite/PostgreSQL, validação de imagens reais, prevenção de uploads órfãos, logout com revogação de sessão, hash de tokens, recuperação de senha, confirmação de e-mail, rate limiting, validação de CPF/CNPJ, índices de banco, redução de N+1 no catálogo e deduplicação de visualizações.

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

## Produção — GitHub + Railway

O `Dockerfile` compila o frontend e serve frontend + API no mesmo serviço. O Railway deve continuar conectado à branch `main` do GitHub. Não é necessária nenhuma variável nova para migrar da V2.18.1 para a V2.18.2.

Após o deploy, valide:

`https://www.classificaja.com.br/api/health`

A resposta deve indicar `"version":"2.18.6"`.

## Migração automática

Se `plan_settings.boost_30` ainda estiver com o limite padrão anterior de 15 anúncios, a V2.18.2 altera automaticamente esse valor para 10. Limites personalizados diferentes de 15 são preservados.

Leia também `LEIA-ME_V2_18_2.txt`, `MIGRACAO_V2_18_2.md` e `VALIDACAO_V2_18_2.md`.

## Fotos no mobile — V2.18.4

O botão **Galeria** agora solicita um único tipo de mídia (`image/*`) e usa o seletor nativo do navegador (`showPicker`) quando disponível. Isso evita o fallback causado por múltiplos MIME types em Chromium/Android e aumenta a chance de abrir diretamente o Photo Picker do sistema.

A aplicação continua aceitando somente **JPG/JPEG, PNG e WEBP**, com até 8 fotos e 7 MB por imagem. O botão **Câmera** permanece separado e usa `capture="environment"`.

> Observação: um site não pode obrigar qualquer navegador Android a abrir um app específico como “Galeria Samsung”. A interface final depende do navegador/SO. Em Chrome/Chromium compatível, o Photo Picker pode ser usado; em navegadores sem suporte, o sistema pode exibir o seletor de arquivos.


## Títulos dos anúncios — V2.18.5

- Na página de detalhes, o título é exibido por completo, inclusive no mobile.
- Nos cards/listagens, o título pode ocupar até 3 linhas para preservar alinhamento e legibilidade.
- Palavras extensas quebram de forma segura sem ultrapassar o card.


## Home clean e carrossel — V2.18.6

- Badges e contadores não ficam mais sobre as fotos dos cards.
- Metadados aparecem em chips discretos abaixo da imagem.
- A seção Ofertas em destaque usa carrossel automático com setas, indicadores e swipe no mobile.
