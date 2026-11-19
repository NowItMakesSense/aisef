---
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.mjs"
  - "**/*.cjs"
description: Praticas de TypeScript e JavaScript
source: ECC rules/typescript (MIT), condensado
---

# TypeScript e JavaScript

- `strict: true` no tsconfig; sem `any` (use `unknown` e estreite); sem `!` e `as` para calar o compilador; `@ts-ignore` só com comentário do porquê.
- Valide dado externo na borda com schema (zod, valibot ou o que o projeto usa) e derive o tipo do schema.
- Uniões discriminadas para estados (`{status: 'ok', data} | {status: 'erro', erro}`) em vez de flags opcionais.
- Toda promessa tem `await` ou `.catch`; nada de `forEach` com `async`; `Promise.allSettled` quando falhas parciais são aceitáveis.
- Imutabilidade: `const`, `readonly`, spread em vez de mutar objeto recebido.
- Sem `eval`/`new Function`; nada de `innerHTML` com dado do usuário; segredo nunca no bundle do cliente (só variáveis com o prefixo público do framework).
- Imports ordenados e sem ciclos; um módulo, uma responsabilidade; `===` sempre.
- Testes com o runner do projeto (vitest, jest); Testing Library na UI, testando pelo que o usuário vê.
