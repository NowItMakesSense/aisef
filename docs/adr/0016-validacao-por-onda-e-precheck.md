# ADR 0016: Validação por onda e precheck determinístico

- **Status:** aceito
- **Data:** 2026-11-18

## Contexto

O modo contínuo funcionava, mas demorava. Cada tarefa custava ao orquestrador três chamadas antes de delegar (pacote, rota, `delegation`), cada uma pagando os hooks. Cada tarefa executada abria um validador completo, inclusive quando faltava algo óbvio, como o relatório ou a evidência de TDD.

## Decisão

- `aisef_project.py dispatch` monta a onda inteira numa chamada: prompt, modelo e effort de cada agente, e os `delegation` já registrados.
- `precheck` é uma checagem determinística, sem modelo e **sem executar comandos do projeto**. Quem falha recebe `task_rejected` do orquestrador e volta ao executor como tentativa + 1. Os testes continuam sendo rodados pelos agentes no Bash, onde o gateway os vê.
- `validate-wave` usa **um** validador para a onda, no nível do executor mais alto (outro modelo quando possível), com veredito por tarefa. A regra "quem executa não valida" continua.
- A auditoria de Edit/Write/MCP roda em segundo plano (`async`). A de Bash/PowerShell continua síncrona, porque consome a aprovação reforçada de uso único.

## Consequências

Menos chamadas por onda (de cerca de 3N para 1 no despacho) e menos validadores. Um validador para várias tarefas tem mais contexto por chamada; ondas muito grandes podem ser divididas pelo orquestrador. Se a versão do Claude Code ignorar `async`, a auditoria só volta a ser síncrona.
