# Validação técnica — ClassificaJá V2.18.2

Testes de backend executados em SQLite isolado:

- Premium padrão = 10 anúncios: OK
- Plus padrão = 5 anúncios: OK
- Cota Plus cheia retorna `quota_full`: OK
- Premium expõe apenas `boost_30` como plano pago permitido: OK
- Premium -> Plus bloqueado no backend: OK
- Plus -> Grátis bloqueado no backend: OK
- Plus vencido permanece identificado e retorna `status=expired`: OK
- Renovação de Plus vencido ativa novamente a conta: OK
- Upgrade Plus -> Premium ativa Premium: OK
- Após upgrade, limite Premium = 10: OK
- Compilação sintática do backend (`py_compile`): OK

O frontend foi atualizado nas telas de escolha de plano, destaque e painel para refletir as mesmas regras de renovação/upgrade.
