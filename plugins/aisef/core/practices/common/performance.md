---
description: Desempenho com medicao no AISEF
source: ECC rules/common/performance.md (MIT), adaptado
---

# Desempenho

- **Meça antes de otimizar:** requisito não funcional com número (latência p95, throughput, memória, tamanho de bundle). Sem medição antes e depois, não é otimização.
- Ataque primeiro o que costuma pesar: I/O em laço, N+1, consulta sem índice, serialização repetida, carga inteira em memória, re-render desnecessário.
- Cache só com regra de invalidação clara e métrica de acerto.
- Tempo limite e limite de recursos em toda chamada externa; paginação em toda listagem.
- Legibilidade não é trocada por micro-otimização sem ganho medido.
