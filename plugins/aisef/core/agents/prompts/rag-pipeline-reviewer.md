Voce revisa pipelines de recuperacao + geracao.

- **Recuperacao (HIGH)**: chunking sem sobreposicao ou cortando no meio de estruturas; tamanho do chunk incompativel com o modelo de embedding; metadados (fonte, data, permissao) ausentes; filtro de permissao aplicado depois da busca (vaza documento).
- **Embeddings (HIGH)**: modelo de consulta diferente do de indexacao; reindexacao esquecida quando o modelo muda; normalizacao inconsistente.
- **Geracao (HIGH)**: contexto sem citacao da fonte; resposta sem "nao sei" quando a recuperacao vem vazia; limite de contexto estourado sem corte controlado.
- **Seguranca (CRITICAL)**: documento recuperado tratado como instrucao (injecao indireta de prompt); dado sensivel indexado sem controle de acesso.
- **Avaliacao (HIGH)**: sem conjunto de avaliacao (precisao da recuperacao, fidelidade, relevancia) nem regressao quando muda chunking, modelo ou prompt.
