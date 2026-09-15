# Migração ClassificaJá V2.18.3

Atualização de frontend para seleção de fotos em mobile. Não há migração de banco nem novas variáveis no Railway.

Arquivos principais alterados:
- `frontend/src/pages/Publish.jsx`
- `frontend/src/pages/EditProduct.jsx`
- `frontend/src/styles.css`
- `frontend/package.json`
- `backend/main.py` (somente identificação da versão)

## Validação
1. Publicar anúncio no celular.
2. Tocar em **Galeria** e selecionar várias fotos.
3. Confirmar prévias e remoção individual.
4. Tocar em **Câmera** e tirar uma foto.
5. Editar anúncio e repetir o fluxo de galeria/câmera.
6. Confirmar `/api/health` com `2.18.3`.
