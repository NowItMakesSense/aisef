---
description: Arquitetura orientada a eventos
source: AISEF
---

# Orientada a eventos

- **Evento é fato no passado** (`PedidoPago`), imutável, com id, data, versão do schema e id de correlação. Comando (`PagarPedido`) é outra coisa.
- **Entrega pelo menos uma vez:** todo consumidor é **idempotente** (dedupe por id do evento) e tolera ordem diferente quando a ordem não é garantida.
- **Outbox transacional:** grave o evento na mesma transação da mudança de estado e publique depois; nunca "salvar e publicar" sem garantia.
- **Erros:** retry com backoff, fila de mensagens mortas (DLQ) monitorada, alerta.
- **Schema dos eventos** versionado (AsyncAPI, registro de schema); evolução compatível.
- Observabilidade: rastreie a cadeia de eventos pelo id de correlação.

## Quando não usar
Fluxos que precisam de resposta imediata e consistência forte entre as partes; times sem estrutura para operar filas (monitoração, DLQ, reprocessamento).
