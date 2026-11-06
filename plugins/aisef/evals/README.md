# Avaliações das skills

Casos para `claude plugin eval`. Cada um verifica se o Claude escolhe a skill certa com um pedido natural e se segue o processo do AISEF.

| Caso | Tag | O que verifica |
|---|---|---|
| `init-trigger` | `trigger` | "Quero usar o AISEF aqui" dispara a `aisef-init`, que pergunta só o mínimo. |
| `negative` | `trigger` | Uma pergunta sem relação não carrega nenhuma skill do AISEF. |
| `quick-choice` | `trigger`, `choice` | Para um typo, o plano é o caminho rápido (`aisef_new.py quick`), não o ciclo completo. |
| `feature-choice` | `trigger`, `choice` | Para uma feature, o plano usa o gerador por brief e para na aprovação do plano. |
| `tooling-choice` | `trigger`, `choice` | Pedir sugestões de ferramentas carrega a `aisef-tooling`, e o plano busca em fontes prontas (find-skills, MCP Registry, marketplaces) e não instala nada sem a escolha do usuário. |
| `tooling-suggest` | `shell` | Executa de fato a busca, grava `.aisef/tooling.md` e não roda nenhum comando de instalação. |
| `quick-path` | `shell` | Executa de fato o caminho rápido e corrige o README. |
| `feature-brief` | `shell` | Executa de fato o gerador e cria o Feature Contract. |

## Como rodar

```
# em qualquer sistema (não precisa de shell):
claude plugin eval plugins/aisef --tag trigger --scaffold --no-publish

# casos que executam comandos: só Linux/macOS, que têm sandbox para o Bash
claude plugin eval plugins/aisef --tag shell --scaffold --allow-tools Bash Write Edit --no-publish
```

O `--scaffold` roda o `scaffold_aisef.sh`, que cria um projeto git com o AISEF iniciado. Ele roda como você, fora do sandbox.

No Windows, o `claude plugin eval` recusa casos que liberam o Bash, porque não há sandbox para confiná-lo. Por isso esses casos têm a tag `shell`.

Resultado em 2026-11-05, rodando no Windows: `init-trigger` 2/2, `negative` 2/2, `feature-choice` 2/2 e `quick-choice` 3/3. O `quick-choice` só chegou a 3/3 depois que a `description` da skill `aisef` passou a citar mudanças pequenas; antes era 1/2.

Resultado em 2026-11-06, no Windows: `tooling-choice` 2/2 com o plugin e 0/2 sem ele. A skill só passou a ser carregada depois que a `description` da `aisef-tooling` deixou de resumir o processo inteiro; antes, o modelo respondia só com o resumo e não carregava a skill. O `negative` continua em 2/2.
