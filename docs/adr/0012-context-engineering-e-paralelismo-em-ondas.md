# ADR 0012: Context engineering e paralelismo em ondas

- **Status:** aceito
- **Data:** 2026-11-06

## Contexto

Agentes que exploram o repositório inteiro gastam tokens; tarefas em série desperdiçam tempo.

## Decisão

- `aisef_context.py pack` monta o pacote da tarefa em camadas: obrigatório, referenciado e sob demanda.
- A memória de projeto fica em `.aisef/knowledge/`, sempre com fonte e sem segredos.
- `aisef_project.py waves` calcula ondas de tarefas prontas (dependências, `parallelizable`, paths sem conflito). Na dúvida sobre conflito, as tarefas vão para ondas diferentes.
- O modo contínuo (`next`) segue sozinho dentro do plano aprovado e para só quando precisa do usuário.

## Consequências

Aprovações continuam do usuário mesmo no modo contínuo.
