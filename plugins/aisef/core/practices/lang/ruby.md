---
paths:
  - "**/*.rb"
  - "**/*.erb"
description: Praticas de Ruby e Rails
source: ECC rules/ruby (MIT), condensado
---

# Ruby e Rails

- RuboCop limpo; Brakeman sem alerta novo.
- Strong parameters sempre; nada de interpolação em `where`/SQL; `html_safe`/`raw` só com HTML confiável.
- Evite N+1 com `includes`; índice em toda chave estrangeira; migrations reversíveis.
- Callbacks só para o próprio dado; efeitos externos (e-mail, API) em job depois do commit.
- Controller fino; regra de negócio em objetos de serviço/domínio; testes com RSpec ou Minitest.
