# ADR 0009: Briefs e caminho rápido

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

Escrever contratos JSON inteiros à mão gasta muitos tokens e erra o schema. E nem toda mudança justifica o ciclo completo.

## Decisão

- O modelo escreve um brief curto e `aisef_new.py` expande, valida e grava os contratos.
- Mudanças pequenas (typo, texto, patch de dependência sem quebra) vão pela feature permanente `FEAT-MAINT`, sem blueprint nem validador independente.
- Avaliações de skills com shell só rodam em Linux e macOS (o Windows não tem sandbox para o Bash).

## Consequências

O plano da `FEAT-MAINT` é aprovado uma única vez. Commit e push continuam pedindo aprovação.
