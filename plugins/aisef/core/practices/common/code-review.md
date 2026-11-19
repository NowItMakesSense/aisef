---
description: Revisao de codigo no AISEF (severidades e veredito)
source: ECC rules/common/code-review.md (MIT), adaptado
---

# Revisão de código

- Toda tarefa passa por revisão antes do validador: o `code-reviewer`, o revisor da linguagem e os especialistas que o roteamento indicar (banco, segurança, arquitetura).
- **Severidades:**
  - **CRITICAL** — segurança, perda ou corrupção de dados. Bloqueia o aceite.
  - **HIGH** — bug provável, quebra da regra de dependência, caminho novo sem teste. Corrigir antes do aceite.
  - **MEDIUM** — manutenção, legibilidade, desempenho fora de caminho quente.
  - **LOW** — sugestão.
- **Veredito:** `APPROVE` sem CRITICAL nem HIGH; `WARNING` com HIGH; `BLOCK` com CRITICAL.
- **Achado tem prova:** `arquivo:linha`, o cenário de falha e por que as proteções existentes não pegam. Revisão sem achado é resultado válido.
- O revisor não corrige: a correção volta ao executor, dentro do mesmo Task Contract.
