---
description: CQRS e event sourcing
source: AISEF
---

# CQRS (e event sourcing)

**CQRS:** separar o modelo de **escrita** (comandos que mudam estado e validam regras) do modelo de **leitura** (consultas otimizadas para a tela).
- Comando não devolve dado de leitura (no máximo id ou resultado da operação); consulta nunca muda estado.
- Um handler por comando e por consulta; validação e autorização no handler do comando.
- O modelo de leitura pode ser uma view, uma tabela desnormalizada ou outro banco — atualizado de forma síncrona ou por evento (consistência eventual explícita na UI).

**Event sourcing:** o estado é derivado de uma sequência de eventos imutáveis (o *event store* é a fonte da verdade); projeções montam os modelos de leitura.
- Eventos versionados e nunca alterados (*upcasting* para mudar o formato); *snapshots* para agregados longos.
- Reprocessar projeções tem que ser possível e testado.

## Quando não usar
CQRS completo em CRUD é complexidade gratuita; comece separando só as consultas pesadas. Event sourcing só quando o histórico **é** o requisito (auditoria, reconstrução temporal, domínio naturalmente por eventos) — ele torna correções, migrações e LGPD (apagar dado) bem mais difíceis.
