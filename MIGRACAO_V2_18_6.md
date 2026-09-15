# Migração ClassificaJá V2.18.6

Atualização visual sobre a V2.18.5.

## Mudanças
- Fotos dos cards ficam livres de badges/textos sobrepostos.
- Informações de destaque, promoção, quantidade de fotos e recência passam para chips discretos abaixo da foto.
- No mobile, metadados redundantes são ocultados para reduzir ruído visual.
- "Ofertas em destaque" virou um carrossel automático com uma oferta por vez.
- Carrossel com setas, indicadores, autoplay e gesto horizontal no mobile.
- Imagem do destaque fica limpa, sem textos sobre a foto.
- Regras de planos, pagamentos, upload, autenticação e banco permanecem inalteradas.

## Deploy
1. Substitua os arquivos alterados no GitHub.
2. Faça commit na branch `main`.
3. Aguarde o Railway concluir o deploy.
4. Confirme `/api/health` com `version: 2.18.6`.
