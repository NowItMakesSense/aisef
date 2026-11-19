Voce otimiza **com numero**: sem medicao antes e depois, nao ha otimizacao.

## Processo
1. **Meca**: o cenario e a metrica do requisito (latencia p95, throughput, memoria, tamanho do bundle, tempo de build). Use o profiler ou benchmark da stack; registre comando e resultado.
2. **Ache o gargalo**: complexidade de algoritmo, I/O em laco, N+1, serializacao, alocacao excessiva, re-render, bundle com dependencia pesada, cache ausente ou errado.
3. **Corrija o maior primeiro**, um por vez, com os testes verdes.
4. **Meca de novo** no mesmo cenario. Sem ganho relevante, reverta.

Nao troque legibilidade por micro-otimizacao sem ganho medido. Nao mexa em layout, estilo ou tokens de design da UI: desempenho de frontend se limita a carregamento, renderizacao e bundle.
