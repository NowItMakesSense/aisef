---
description: Fluxo de desenvolvimento do AISEF (pesquisar, especificar, fatiar, TDD, revisar, validar)
source: ECC rules/common/development-workflow.md (MIT), adaptado ao ciclo do AISEF
---

# Fluxo de desenvolvimento

0. **Pesquise e reuse primeiro (search-first):** antes de escrever, procure no repositório, na biblioteca padrão, em pacotes mantidos, em skills e em MCPs algo que resolva 80% do problema. Registre a escolha: adotar, estender ou construir — e por quê.
1. **Descoberta** (`aisef-discovery`): investigar antes de perguntar; nunca inventar regra de negócio.
2. **Spec e fatias** (`aisef-feature`): requisitos verificáveis, seams de teste aprovados, fatias verticais demonstráveis.
3. **Blueprint:** onde cada parte mora segundo o estilo de arquitetura adotado (`.aisef/architecture.json`).
4. **TDD** por fatia, dentro do escopo do Task Contract.
5. **Revisão** (avaliadores) → **validação independente** (validator) → **aceite** do usuário.
6. **Verificação antes de concluir** (`aisef_project.py verify-loop`): build, tipos, lint, testes, varredura de segredos e diff.
