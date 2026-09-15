# ClassificaJá V2.18.15

Marketplace/classificados com frontend React/Vite e backend FastAPI. A V2.18.13 mantém as correções anteriores e adiciona um rodapé profissional com Central de Atendimento integrada ao Painel Master.

## Fluxo direto de publicação — V2.18.9

Contas com plano ativo e vagas disponíveis agora entram diretamente no formulário ao tocar em **Anunciar**. A tela de planos só aparece quando realmente é necessária: plano inexistente, vencido ou cota cheia.

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

O `Dockerfile` compila o frontend e serve frontend + API no mesmo serviço. O Railway deve continuar conectado à branch `main` do GitHub. Não é necessária nenhuma variável nova para a V2.18.13.

Após o deploy, valide:

`https://www.classificaja.com.br/api/health`

A resposta deve indicar `"version":"2.18.15"`.

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


## Home clean e carrossel — V2.18.8

- Badges e contadores não ficam mais sobre as fotos dos cards.
- Metadados aparecem em chips discretos abaixo da imagem.
- A seção Ofertas em destaque usa carrossel automático com setas, indicadores e swipe no mobile.


## Carrossel Premium e imagens padronizadas — V2.18.8

- O carrossel de ofertas em destaque usa uma área visual fixa por breakpoint.
- A foto principal usa `object-fit: contain`, preservando toda a imagem sem deformar.
- Uma cópia desfocada da própria foto preenche o fundo, evitando faixas vazias e diferenças visuais entre fotos verticais, quadradas e horizontais.
- Notebook/desktop médio: carrossel compacto com largura máxima de 900 px e altura de 280 px.
- Desktop grande: largura máxima de 1080 px e altura de 360 px.
- Mobile: proporção 16:10, mantendo a foto inteira e responsiva.
- O bloco recebeu acabamento premium: moldura suave, faixa de destaque, selo, sombra, CTA e navegação refinados.


## Rodapé e Central de Atendimento — V2.18.13

- Rodapé profissional com atalhos para **Reclamações**, **Suporte** e **Sugestão**.
- Cada opção abre uma central de atendimento com formulário próprio.
- Usuários logados têm nome/e-mail vinculados automaticamente; visitantes também podem enviar informando os dados.
- Cada envio recebe um protocolo curto e fica registrado no banco.
- Novo menu **Painel Master → Atendimento** para visualizar e resolver solicitações.
- Botão flutuante de **voltar ao topo** aparece após a rolagem e respeita a navegação fixa do mobile.


## Painel Master interativo — V2.18.13

Os cards principais da Visão geral agora funcionam como atalhos reais:

- **Contas** → gerenciamento de contas.
- **Anúncios** → gerenciamento de anúncios.
- **Visualizações** → ranking dos anúncios mais vistos.
- **Destaques ativos** → relação dos anúncios com destaque ativo.
- **Receita** → pagamentos e financeiro.
- **Atendimentos** → Central de Atendimento.
- **Denúncias** → moderação de denúncias.

Os cards receberam estados de hover/foco e indicação visual de ação. Não há nova variável de ambiente para esta atualização.


## Painel do usuário interativo — V2.18.13

Os blocos de métricas da visão geral também são atalhos funcionais:

- **Anúncios** abre Meus anúncios;
- **Ativos** abre Meus anúncios filtrando somente os ativos;
- **Visualizações** abre os anúncios ordenados do mais visto para o menos visto;
- **Favoritos recebidos** abre os anúncios ordenados pelo número de favoritos;
- **Mensagens não lidas** abre o Chat.

A tela **Meus anúncios** passou a exibir visualizações e favoritos recebidos por anúncio e entende os filtros/ordenações vindos do painel.

## Hotfix do Painel Master — V2.18.13

A V2.18.13 corrige a tela branca em `/admin` causada por ordem inconsistente de hooks React durante o carregamento. Os cards funcionais e rankings da V2.18.11 foram preservados. Não há nova variável de ambiente nem alteração de banco nesta hotfix.

## Notificações Push — V2.18.13

A V2.18.13 adiciona notificações push reais no navegador, com Service Worker e Web Push/VAPID.

No **Painel do usuário → Notificações**, cada pessoa pode:

- ativar ou desativar os alertas;
- receber apenas anúncios da própria cidade;
- escolher uma categoria preferida ou todas;
- receber apenas anúncios em destaque;
- enviar uma notificação de teste para o aparelho.

Quando um novo anúncio é publicado, o backend envia push apenas para usuários com a opção ativa e cujos filtros correspondem ao anúncio. O próprio anunciante nunca recebe alerta do próprio anúncio.

As inscrições do navegador ficam vinculadas à conta e armazenadas no banco. Inscrições expiradas (HTTP 404/410 do serviço push) são desativadas automaticamente.

### Chaves VAPID

Por padrão **não é necessário criar novas variáveis no Railway**. Na primeira utilização, o backend gera uma chave VAPID P-256 uma única vez e guarda a chave privada de forma persistente no banco (criptografada quando `PAYMENT_CONFIG_KEY` ou `ACCOUNT_TOKEN_SECRET` está disponível).

Opcionalmente, instalações que desejarem controlar suas próprias chaves podem definir `PUSH_VAPID_PRIVATE_KEY`, `PUSH_VAPID_PUBLIC_KEY` e `PUSH_VAPID_SUBJECT`.

### Compatibilidade

Produção deve usar HTTPS. Chrome/Edge no Android oferecem o fluxo principal. O formato visual final da notificação é controlado pelo sistema operacional/navegador.



## V2.18.15 — Retenção de usuários

A Central de Notificações do painel agora separa os alertas de descoberta dos alertas relacionados aos próprios anúncios. O usuário pode ativar/desativar individualmente: novas mensagens, novos favoritos, desempenho diário, vencimento/expiração, resumo semanal, lembrete de retorno e novos anúncios do marketplace.

O backend envia mensagens e favoritos imediatamente e roda um ciclo idempotente de retenção para lembretes programados. Para evitar spam, existe prioridade entre lembretes e no máximo um lembrete programado por usuário a cada 24 horas.

Não é obrigatório adicionar novas variáveis no Railway. Opcionalmente, `RETENTION_ENABLED=false` desliga o ciclo automático e `RETENTION_LOOP_SECONDS` altera o intervalo (mínimo de 900 segundos).
