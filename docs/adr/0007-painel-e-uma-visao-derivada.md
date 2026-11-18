# ADR 0007: Painel é uma visão derivada

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

O usuário precisa acompanhar o projeto, mas um painel editável viraria uma segunda fonte de verdade.

## Decisão

- O painel lê os contratos e o log e nunca é fonte de verdade. Mermaid gera os diagramas.
- Com a integridade do log comprometida, o painel continua mostrando os dados, com um banner vermelho, para permitir a investigação.

## Consequências

Decisões continuam no Approval Center (skill `aisef-approve`), pelo prompt nativo.
