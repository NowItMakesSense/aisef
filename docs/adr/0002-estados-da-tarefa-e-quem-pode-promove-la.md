# ADR 0002: Estados da tarefa e quem pode promovê-la

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

Agentes tendem a declarar o próprio trabalho como pronto. É preciso separar "terminou" de "está certo".

## Decisão

- Estados: `draft`, `ready`, `in_progress`, `executed` (o agente terminou), `validated` (critérios verificados por outro agente), `completed` (o orquestrador aceitou e integrou), além de `blocked`, `rejected` e `cancelled`.
- `executed` no Execution Report significa só que o agente terminou. Quem promove é o validador e, depois, o orquestrador.
- Subtarefa usa o mesmo schema do Task Contract, com `kind: "subtask"` e `parent_task_id`.

## Consequências

O `aisef-check` acusa autovalidação (`VAL-SELF-ATTEST`) e validação ausente (`STATE-NO-VALIDATION`).
