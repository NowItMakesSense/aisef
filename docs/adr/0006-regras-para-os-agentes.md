# ADR 0006: Regras para os agentes

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

Vários agentes trabalhando ao mesmo tempo precisam de regras de comunicação e de limites individuais.

## Decisão

- Toda comunicação passa pelo orquestrador; especialistas não delegam nem falam entre si.
- O agente não altera escopo, decisões nem contratos, mas pode contestar com evidências.
- O agente não valida o próprio trabalho. A memória pertence ao projeto.
- O Agent Contract define só um **teto** de permissão; a permissão efetiva vem da política e da autorização.
- O validador só usa Git de leitura. Um agente só fica `active` com aprovação do usuário.

## Consequências

O gateway aplica o teto de cada subagente. Os agentes são gerados de uma fonte única (`tools/gen_agents.py`).
