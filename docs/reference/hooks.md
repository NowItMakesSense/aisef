# Hooks

Declarados em [`plugins/aisef/hooks/hooks.json`](../../plugins/aisef/hooks/hooks.json) e carregados por `run.sh`, que sai na hora em projetos sem `.aisef/config.json`: o plugin não interfere em outros projetos.

| Evento | Matcher | Script | O que faz | Falha |
|---|---|---|---|---|
| `SessionStart` | `startup\|resume\|compact` | `doctor.py` | Avisa se falta Python, `jsonschema`, `cryptography`, chave ou se há agente em draft. Depois de `/compact` ou `/resume`, reinjeta um resumo curto do estado (fase, em andamento, decisões pendentes). Em silêncio quando não há nada a dizer | aberta (só avisa) |
| `PreToolUse` | `Bash\|PowerShell\|Read\|Edit\|Write\|MultiEdit\|NotebookEdit\|Grep\|Glob\|WebFetch\|mcp__.*` | `gateway.py` | Aplica a [política](policy.md) e o teto do Agent Contract. Para Grep e Glob, também devolve o lembrete consultivo do grafo de código, no mesmo processo | **fechada** (erro vira `deny`) |
| `PostToolUse` | `Bash\|PowerShell` | `audit_hook.py` | Anexa `tool_used` ao log assinado (comando sem segredo) e marca a aprovação reforçada consumida. Síncrono, para o uso único valer já na chamada seguinte | aberta (avisa em stderr) |
| `PostToolUseFailure` | `Bash\|PowerShell` | `audit_hook.py` | O mesmo registro para o comando que **falhou**, com o `exit_code` tirado da primeira linha `Exit code N` (E-01). Sem isso o vermelho do TDD nunca chegava ao log. Síncrono, como o `PostToolUse` do shell | aberta (avisa em stderr) |
| `PostToolUse` | `Edit\|Write\|MultiEdit\|NotebookEdit\|mcp__.*` | `audit_hook.py` | O mesmo registro, **em segundo plano** (`async`): não segura a sessão. MCP só com os nomes dos campos | aberta |

| `SubagentStart` / `SubagentStop` | (todos) | `agent_events.py` | Registram início e fim de cada subagente em `.aisef/runtime/agents.jsonl` (efêmero, fora do Git) para o mapa de execução do painel. Em segundo plano | aberta (silêncio) |
| `PreToolUse` | `Agent\|Task` | `agent_events.py` | Registra **quem disparou quem**: o agente que chamou, o tipo do subagente, o pedido (`description`) e o modelo. O painel liga esse registro ao `SubagentStart` seguinte do mesmo tipo e marca a ligação como inferida quando não há como ter certeza. Em segundo plano, nunca bloqueia (0.10.0) | aberta (silêncio) |

| `UserPromptSubmit` | (todos) | `prompt_mode.py` | No modo Ask, lembra o modelo de responder sem editar nem executar. Em silêncio no modo normal | aberta |

## Python
O `run.sh` usa `AISEF_PYTHON`, se definido (o mais rápido); senão, o primeiro `python3`/`python`/`py` do PATH, pulando o atalho da Microsoft Store. Sem Python, o gateway nega (falha fechada) e a auditoria avisa.

## Latência
Cada hook abre um processo Python. Meça com `python tools/bench_hooks.py`. No Windows, a mediana fica entre ~170 e ~270 ms por hook.
