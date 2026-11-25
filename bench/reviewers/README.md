# Revisores com bugs plantados (M-07)

Mede se cada revisor do AISEF acha o bug que está na mudança e se fica quieto quando a mudança está certa. O
harness é `tools/bench_reviewers.py`. O resultado alimenta a C-05: cortar o agente que não se paga.

| Categoria | Casos | Revisores do escopo |
|---|---|---|
| `security` | SQL injection, path traversal, injeção de comando, segredo no código, `pickle` de dado do cliente | `security`, `code-reviewer` |
| `sql` | `UPDATE` sem `WHERE`, coluna comparada com ela mesma, N+1 | `database-reviewer`, `code-reviewer` |
| `types` | `Optional` sem checar `None`, soma de strings escondida por `as number` | `type-design-analyzer`, `code-reviewer` |
| `silent-failure` | `except: pass`, erro de rede virando saldo zero | `silent-failure-hunter`, `code-reviewer` |
| `weak-test` | teste sem asserção de valor, teste que faz mock da função testada | `pr-test-analyzer`, `code-reviewer` |
| `logic` | off-by-one na paginação, lista padrão mutável | `code-reviewer` |
| `clean` | refatoração, busca parametrizada, testes bons, erro com contexto | todos |

O revisor da linguagem (`python-reviewer`, `typescript-reviewer`, `database-reviewer` para `.sql`) entra em todo caso
daquela linguagem.

## Estrutura de cada caso

- `case.json`: `id`, `category`, `file` e `bug` (`match`, o trecho único da linha do bug; `description`;
  `keywords`). Nos casos limpos, `bug` é `null`.
- `before/` e `after/`: o arquivo antes e depois. O revisor recebe o diff e a pasta `after/`.

## Como rodar

```
python tools/bench_reviewers.py --check-fixtures      # sem custo; roda no run_tests.py
python tools/bench_reviewers.py --run --model sonnet  # gasta tokens: 73 chamadas por repetição
python tools/bench_reviewers.py --score docs/benchmarks/reviewers-<data>.json   # recalcula sem modelo
```

Um achado acerta quando cai no arquivo do bug e a até 3 linhas dele, ou quando cita uma das palavras-chave. Falso
alarme é um caso limpo com achado `medium` ou mais grave. Veredito por agente: **paga** (recall de pelo menos 60% e
falso alarme de até 25%), **cortar?** (recall abaixo de 30%) ou **revisar**.
