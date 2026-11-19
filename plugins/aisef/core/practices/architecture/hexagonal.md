---
description: Arquitetura hexagonal (ports and adapters)
source: AISEF, inspirado na skill hexagonal-architecture do ECC (MIT)
---

# Hexagonal (ports and adapters)

**Ideia:** a aplicação é um hexágono com **portas** (interfaces) e o mundo externo se conecta por **adaptadores**.

- **Portas de entrada (driving/primárias):** o que a aplicação oferece — casos de uso. Adaptadores de entrada: HTTP, CLI, consumidor de fila, testes.
- **Portas de saída (driven/secundárias):** o que a aplicação precisa — repositórios, gateways de pagamento, notificação. Adaptadores de saída: Postgres, Stripe, SMTP, fakes de teste.
- O núcleo define as portas na **sua** linguagem (`ObterCliente`, não `SELECT`). Adaptador traduz e não decide regra.
- **Teste:** o núcleo inteiro roda com adaptadores falsos em memória; cada adaptador real tem teste de integração próprio (contrato da porta).

## Sinais de problema
Porta que vaza o detalhe (`salvarNoPostgres`, tipos do ORM na assinatura); adaptador com regra de negócio; núcleo importando o SDK do provedor.

## Quando não usar
Sistema pequeno com uma só entrada e uma só saída estável: as portas custam mais do que protegem.
