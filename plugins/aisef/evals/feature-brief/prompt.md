---
description: Feature nova deve ser especificada com um brief curto pelo gerador (aisef_new.py feature), sem escrever o contrato JSON a mao, e terminar pedindo aprovacao do plano.
tags: [behavior, tokens, shell]
runs: 1
max_turns: 20
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit]
---

Quero uma feature nova neste projeto: aplicar cupom de desconto percentual no total do carrinho (src/carrinho.py). Requisitos que eu defino: o desconto vai de 1% a 50%; cupom invalido e recusado com erro claro. Fora do escopo: cupons de frete. Especifique pelo processo do AISEF e pare quando o plano estiver pronto para eu aprovar.
