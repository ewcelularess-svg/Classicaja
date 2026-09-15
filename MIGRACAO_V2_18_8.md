# Migração ClassificaJá V2.18.8

## Objetivo
Padronizar o tamanho das imagens do carrossel e elevar o acabamento visual da seção **Ofertas em destaque**.

## Alterações
- Imagens do carrossel não são mais esticadas ou deformadas.
- Fotos verticais, quadradas e horizontais ocupam uma área fixa e previsível.
- A imagem principal permanece inteira (`object-fit: contain`).
- O fundo usa a própria foto ampliada e desfocada para eliminar espaços vazios agressivos.
- Notebook: 900 px de largura máxima / 280 px de altura.
- Desktop grande: 1080 px / 360 px.
- Mobile: proporção 16:10.
- Novo acabamento premium com borda, faixa superior, sombras, selo e controles refinados.

## Deploy
1. Substitua os arquivos alterados no repositório GitHub.
2. Faça commit na branch `main`.
3. Aguarde o deploy automático do Railway.
4. Confirme `/api/health` com `version: 2.18.8`.

Nenhuma variável nova de ambiente é necessária.
