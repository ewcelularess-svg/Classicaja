# Migração ClassificaJá V2.18.2

A atualização é compatível com a V2.18.1 e não exige alteração manual no Supabase nem novas variáveis no Railway.

## Limites

- `boost_7`: 1 anúncio
- `boost_15`: 5 anúncios
- `boost_30`: **10 anúncios**

No startup, o backend executa uma migração segura: somente `boost_30` que ainda estiver exatamente com `ad_limit=15` é atualizado para `10`. Valores personalizados diferentes de 15 permanecem intactos.

## Travamento comercial

O backend passa a aplicar as mesmas regras exibidas no frontend:

- Premium -> somente renovação Premium.
- Plus -> renovação Plus ou upgrade Premium.
- Plus/Premium -> não podem voltar ao Grátis.
- Plano pago vencido -> publicação bloqueada até renovação/upgrade válido.

Essas verificações também são feitas na API, evitando contorno manual pelo navegador.

## Renovação

Pagamento confirmado pela página de planos ativa/renova o plano da conta imediatamente. Se ainda houver validade, os novos dias são somados ao vencimento existente. Os anúncios ativos acompanham a validade e o nível do plano da conta.

A cota continua sendo de anúncios cadastrados. Renovação não cria vagas adicionais quando a cota já está cheia.

## Railway

Envie os arquivos para a branch `main` do repositório conectado. Aguarde o deploy automático e valide:

`https://www.classificaja.com.br/api/health`

Deve retornar `"version":"2.18.2"`.
