# ADR 0003: Limites de tentativas e escalonamento

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

Sem limite, um agente pode tentar corrigir indefinidamente, gastando tokens e mascarando um problema de especificação.

## Decisão

- Padrão: 3 correções automáticas, 1 consulta a especialista, depois escala ao usuário.
- Uma tarefa pode reduzir esses limites. Aumentá-los exige aprovação do usuário.
- Risco crítico para a execução na hora.

## Consequências

Os valores ficam em `core/orchestration-defaults.v0.1.json`. Cada tentativa que falha sobe um nível no roteador de modelo (ADR 0010).
