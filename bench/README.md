# Benchmark de resultado

> Revisores: o conjunto de bugs plantados está em [`reviewers/`](reviewers/README.md) (M-07).

Mede se o AISEF entrega código mais correto que o Claude Code puro, usando **testes escondidos** que o agente nunca vê. O harness é `tools/bench_outcomes.py`. É a tarefa M-03 do [plano](../docs/plan/melhorias-0.11-0.14.md).

| Tarefa | Tipo | O que mede |
|---|---|---|
| `feat-slugify` | feature | regras explícitas com casos de borda (acentos, corte sem partir palavra) |
| `feat-reset-token` | feature | expiração na borda, uso único, invalidação do token anterior |
| `bug-pagination` | bug | última página parcial, arredondamento, entradas inválidas |
| `bug-split-bill` | bug | centavos perdidos, distribuição do resto |
| `refactor-shipping` | refatoração | comportamento idêntico, inclusive erros, com menos ramificações |
| `sec-path-traversal` | segurança | `..`, caminho absoluto, pasta vizinha com prefixo igual |

## Estrutura de cada tarefa

- `task.json`: o pedido e o comando dos testes escondidos;
- `repo/`: o que o agente recebe;
- `hidden/`: os testes escondidos, copiados para a pasta só depois que o agente termina;
- `solution/`: a solução de referência, usada só para validar o fixture.

## Como rodar

```
python tools/bench_outcomes.py --check-fixtures   # sem custo; roda no run_tests.py
python tools/bench_outcomes.py --prepare-only     # sem custo; monta os dois braços e confere o AISEF
python tools/bench_outcomes.py --run --arms plain,aisef,aisef-lean --reps 3 --model sonnet   # gasta tokens; Linux ou WSL
```

Braços: `plain` (Claude Code puro), `aisef` (ciclo completo), `aisef-norev` (completo sem os revisores especializados) e `aisef-lean` (a triagem real do AISEF no perfil solo: caminho enxuto quando ela der lean, completo quando der full; hoje 5 das 6 tarefas vão pelo enxuto e `sec-path-traversal` pelo completo).

O resultado vai para `docs/benchmarks/outcomes-<data>.md` (tabela) e `.json` (cada execução).

## Regras para não enviesar

- **O mesmo pedido nos dois braços.** No braço AISEF, o harness faz só o papel do usuário: gera a feature a partir do pedido e aprova o plano. O agente segue o resto sozinho.
- **Os testes escondidos não estão no repositório que o agente vê,** e a pasta `hidden/` é recriada depois da execução.
- **Adicionar uma tarefa:** ela precisa passar em `--check-fixtures`, ou seja, falhar no repositório inicial e passar com a solução de referência.
