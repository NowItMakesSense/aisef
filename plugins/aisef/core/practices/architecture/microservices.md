---
description: Microsservicos - quando e como
source: AISEF
---

# Microsserviços

**Use só com motivo concreto:** times independentes que precisam publicar sem coordenar, partes com escala ou requisitos muito diferentes, isolamento de falha. Sem isso, um monólito modular entrega o mesmo desenho com muito menos custo.

- **Um serviço por contexto delimitado**, dono dos próprios dados (banco por serviço). Nunca dois serviços na mesma tabela.
- **Contratos explícitos e versionados** (OpenAPI, AsyncAPI, protobuf) — veja `contract-first`. Compatibilidade para trás; mudança quebrando exige nova versão.
- **Comunicação:** prefira eventos assíncronos entre contextos; chamada síncrona com tempo limite, retry com backoff e circuit breaker.
- **Consistência:** sem transação distribuída; use sagas (orquestradas ou coreografadas) com compensação, *outbox* para publicar evento junto com a mudança de estado e consumidores idempotentes.
- **Operação:** logs estruturados com id de correlação, tracing distribuído, métricas e health checks por serviço; deploy e rollback independentes.

## Sinais de problema
"Monólito distribuído": serviços que precisam ser publicados juntos, banco compartilhado, cadeias longas de chamadas síncronas, um serviço que conhece o modelo interno de outro.
