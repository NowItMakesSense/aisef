# ADR 0001: Reabertura de feature é um novo ciclo

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

Uma feature aceita pode precisar mudar: defeito, requisito novo ou evolução. Editar o contrato aceito apagaria a evidência do que foi entregue e aprovado.

## Decisão

- Reabrir uma feature cria um novo ciclo (`cycle` + 1). A entrega, as evidências e a aprovação anteriores ficam congeladas.
- O motivo é classificado como `defect`, `requirement_change` ou `evolution`.
- O novo ciclo exige Impact Analysis, contratos e tarefas só para a mudança e um novo aceite.

## Consequências

A história de cada feature fica auditável. O custo é mais cerimônia para correções pós-aceite, que podem ir pelo caminho rápido quando não mudam comportamento.
