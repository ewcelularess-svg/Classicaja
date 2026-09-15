# Validação técnica — ClassificaJá V2.18.6

Validações executadas no pacote:
- `backend/main.py` compilado com `python -m py_compile` sem erro.
- `frontend/package.json` validado como JSON.
- CSS com chaves estruturais balanceadas.
- Componentes alterados conferidos estruturalmente e referências de classes cruzadas com o CSS.
- `ProductCard` não renderiza mais badges dentro da área da foto.
- Home possui carrossel de ofertas com autoplay, setas, indicadores e swipe.
- Backend e frontend marcados como versão `2.18.6`.
- ZIPs reabertos/testados após compactação.

Observação: o build Vite completo será executado pelo Railway durante o deploy, que instala as dependências npm no ambiente de build.
