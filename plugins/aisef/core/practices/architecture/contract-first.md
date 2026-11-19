---
description: Contract-first - o contrato e a fonte da verdade
source: AISEF, inspirado na skill contract-first do ECC (MIT)
---

# Contract-first

- O **contrato** (OpenAPI para HTTP, AsyncAPI para eventos, protobuf/gRPC, JSON Schema) é escrito e aprovado **antes** da implementação e versionado no repositório.
- Código de servidor, cliente e validação é **gerado** ou **validado** contra o contrato; teste de contrato (consumer-driven, como Pact, ou validação de schema) roda no CI.
- Mudança compatível: só adicionar campos opcionais. Remover ou mudar tipo = nova versão, com período de convivência e aviso de descontinuação.
- Erros também fazem parte do contrato (formato e códigos).
- No AISEF, os endpoints do Engineering Blueprint apontam para o contrato; o `code-architect` e o `architecture-reviewer` conferem a aderência.

## Quando não usar
API interna de um único consumidor que muda junto com ele (mesmo repositório, mesmo deploy): o contrato formal pode esperar até aparecer o segundo consumidor ou um time diferente.
