# ADR 0005: Log de auditoria assinado com head externo

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

Um log que o próprio agente pode reescrever não serve como evidência.

## Decisão

- Cada evento é encadeado por hash e assinado com Ed25519. Quem verifica conhece só as chaves públicas.
- O head assinado e a chave privada ficam fora do repositório (`~/.aisef/`).
- Checkpoints assinados, segmentos arquivados, rotação de chave (a antiga é aposentada) e âncoras locais em `~/.aisef/anchors/`.

## Consequências

Truncar ou reescrever o log é detectado. A âncora em serviço externo foi descartada (ver o [roadmap](../roadmap.md)): exigiria aprovação de push a cada checkpoint, e a âncora local fora do repositório cobre o uso individual.
