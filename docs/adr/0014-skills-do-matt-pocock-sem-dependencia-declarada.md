# ADR 0014: Skills do Matt Pocock sem dependência declarada no plugin

- **Status:** aceito
- **Data:** 2026-11-18

## Contexto

O fluxo SDD + TDD usa skills do plugin `mattpocock-skills` (`grilling`, `domain-modeling`, `tdd`, `code-review`). O `plugin.json` aceita `dependencies`, mas o Claude Code não instala uma dependência de outro marketplace (o do Matt é o `claude-plugins-official`) e, sem ela, **o plugin dependente deixa de carregar**. Além disso, `to-spec`, `to-tickets` e `implement-spec` têm `disable-model-invocation: true`: o modelo não consegue chamá-las, e elas publicam no issue tracker.

## Decisão

- O AISEF **não declara** a dependência. O `aisef-init` oferece instalar o plugin no escopo do projeto, com aprovação.
- O agente `implementer` pré-carrega `mattpocock-skills:tdd` pelo campo `skills:`. Se o plugin não existir, o Claude Code pula o nome, e o agente segue as regras de TDD que o próprio AISEF traz.
- O método de `to-spec`, `to-tickets` e `implement-spec` é incorporado às fases Spec e Fatias da `aisef-feature` e ao modo contínuo, com o resultado em `.aisef/` (uma fonte de verdade, com RTM). A atribuição está em `skills/aisef-feature/references/spec-and-slices.md`.
- O `next` mapeia os comandos do Matt para o equivalente no AISEF (`guide.matt_equivalents`).

## Consequências

O AISEF funciona com ou sem o plugin do Matt; com ele, ganha as skills mantidas pelo autor. O `/setup-matt-pocock-skills` (tracker e labels) não é usado em projetos AISEF.
