# ADR 0015: Uma autoridade de design por projeto

- **Status:** aceito
- **Data:** 2026-11-18

## Contexto

O usuário quer usar várias skills de design prontas (Impeccable, Taste, UI/UX Pro Max) para ter sempre a melhor tipografia, disposição e componentes. Juntas, elas trazem três fontes de tipografia, duas de paleta e regras de movimento contraditórias. Sem um árbitro, cada fatia sairia com um visual diferente.

## Decisão

- `.aisef/design/tokens.json` (schema `design-tokens`) e `DESIGN.md` são a autoridade de design, aprovada como `architecture_decision`.
- As skills de design são fontes (UI/UX Pro Max = dados, Taste = direção de arte só em sites, Impeccable = execução e detector) e trabalham **dentro** dos tokens. Valor fora deles vira proposta de mudança, não código.
- `design_check.py scan` confere, sem modelo, cores e fontes do código de UI contra os tokens. Ele vira critério de aceite automático das fatias de UI. `design_check.py shots` gera a evidência visual.
- O gateway nega abrir o Claude sem permissões e pede aprovação para o modo `live` do Impeccable.
- O padrão do papel `frontend` sobe para L3 (sonnet/medium).

## Consequências

Consistência visual verificável entre fatias e agentes. O custo é uma decisão a mais no início de projetos com UI (`DESIGN-MISSING` avisa enquanto não houver). O `scan` cobre cores e fontes; espaçamento e composição continuam com o Impeccable e com a revisão do `frontend`.
