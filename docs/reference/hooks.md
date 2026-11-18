# Hooks

Declarados em [`plugins/aisef/hooks/hooks.json`](../../plugins/aisef/hooks/hooks.json) e carregados por `run.sh`, que sai na hora em projetos sem `.aisef/config.json`: o plugin não interfere em outros projetos.

| Evento | Matcher | Script | O que faz | Falha |
|---|---|---|---|---|
| `SessionStart` | `startup\|resume` | `doctor.py` | Avisa se falta Python, `jsonschema`, `cryptography`, chave ou se há agente em draft. Em silêncio quando está tudo certo | aberta (só avisa) |
| `PreToolUse` | `Bash\|PowerShell\|Read\|Edit\|Write\|MultiEdit\|NotebookEdit\|Grep\|Glob\|WebFetch\|mcp__.*` | `gateway.py` | Aplica a [política](policy.md) e o teto do Agent Contract. Para Grep e Glob, também devolve o lembrete consultivo do grafo de código, no mesmo processo | **fechada** (erro vira `deny`) |
| `PostToolUse` | `Bash\|PowerShell` | `audit_hook.py` | Anexa `tool_used` ao log assinado (comando sem segredo) e marca a aprovação reforçada consumida. Síncrono, para o uso único valer já na chamada seguinte | aberta (avisa em stderr) |
| `PostToolUse` | `Edit\|Write\|MultiEdit\|NotebookEdit\|mcp__.*` | `audit_hook.py` | O mesmo registro, **em segundo plano** (`async`): não segura a sessão. MCP só com os nomes dos campos | aberta |

## Python
O `run.sh` usa `AISEF_PYTHON`, se definido (o mais rápido); senão, o primeiro `python3`/`python`/`py` do PATH, pulando o atalho da Microsoft Store. Sem Python, o gateway nega (falha fechada) e a auditoria avisa.

## Latência
Cada hook abre um processo Python. Meça com `python tools/bench_hooks.py`. No Windows, a mediana fica entre ~170 e ~270 ms por hook.
