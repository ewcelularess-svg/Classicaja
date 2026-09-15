# Validação técnica — ClassificaJá V2.18.3

## Alterações
- botão **Galeria** destacado na publicação mobile;
- botão **Câmera** separado, usando `capture="environment"`;
- seleção múltipla de imagens preservada;
- novas seleções podem ser acrescentadas até 8 fotos;
- remoção individual de prévias antes da publicação;
- mesmo fluxo aplicado ao editor de anúncio;
- regras de planos da V2.18.2 preservadas.

## Verificações realizadas
- `backend/main.py` compila com `py_compile`;
- referências de versão atualizadas para `2.18.3`;
- não há migração de banco nem variável nova no Railway.

## Observação
O build Vite não foi executado neste ambiente porque as dependências npm não estão disponíveis localmente e a instalação externa expirou por timeout. A alteração JSX foi revisada estruturalmente e usa apenas APIs/ícones já presentes no projeto. O Railway fará o build definitivo ao receber o commit.
