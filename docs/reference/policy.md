# Política de permissões

A fonte é [`plugins/aisef/core/permission-policy.v0.1.json`](../../plugins/aisef/core/permission-policy.v0.1.json). As exceções do projeto ficam em `.aisef/policy.local.json` e **só podem deixar a política mais restritiva**. As decisões que a definiram estão no [ADR 0004](../adr/0004-matriz-de-permissoes.md).

## Níveis

| Nível | O gateway devolve |
|---|---|
| `allow` | Nada: o fluxo normal do Claude Code segue |
| `approve_scope` | Nada, se uma autorização de escopo ativa cobre recurso, ambiente e validade; senão, `ask` |
| `approve_operation` | `ask`: o prompt nativo, que o modelo não consegue responder |
| `approve_reinforced` | `ask` só se houver uma reforçada aprovada, válida e não usada para a operação exata; senão, `deny` |
| `deny` | `deny` |

Em `bypassPermissions`, o que pediria aprovação vira `deny`. Erro interno do gateway também vira `deny` (falha fechada).

## Como o gateway classifica

| O que | Como fica (em dev) |
|---|---|
| **Git:** status, log, diff, show, blame, fetch | livre |
| **Git:** commit, push, pull request (`gh pr create`), merge, release, tag | aprovação por operação, cada uma a sua |
| **Git:** force push, `commit --amend`, rebase, `reset --hard`, apagar branch | reforçada |
| **Descartar trabalho local:** `git clean -f`, `checkout --`, `restore`, `stash drop` | sobe um nível (T1) |
| **Arquivos sensíveis:** `.env`, chaves, credenciais (por Read, Edit ou comando) | aprovação por operação |
| **Banco:** CLIs, URLs de conexão, migrations, shell em container | negado (ambiente desconhecido = produção) |
| **Deploy e infraestrutura** | negado (ambiente desconhecido = produção) |
| **Código ofuscado ou baixado** (`curl \| sh`, `base64 -d \| bash`, `eval`, `iex`) | aprovação por operação |
| **Remoção recursiva:** `rm -rf`, `Remove-Item -Recurse`, `rd /s` | sobe um nível (T1) |
| **Instalar skill, plugin, marketplace ou MCP** | aprovação por operação |
| **Config, CI e IaC:** workflows, Dockerfile, compose, Terraform, `.claude/settings`, `.mcp.json` | aprovação por escopo |
| **Ferramentas MCP fora de `mcp_allow`** | aprovação por operação |
| **WebFetch com token na URL** | negado |
| **Log de auditoria e chaves do AISEF** | negado (só o hook de auditoria grava) |
| **Aprovações, autorizações, Agent Contracts e `config.json`** (por Edit, Write ou shell) | aprovação por operação |

Bash e PowerShell seguem exatamente as mesmas regras.

## Teto do Agent Contract (subagentes)
Para um subagente com Agent Contract, o gateway aplica primeiro o teto:
- agente em `draft` é bloqueado;
- recurso fora de `permission_ceiling.resources` é negado;
- operação Git fora de `git_operations` é negada (o `validator` só lê);
- registrar decisão do usuário é sempre negado.

Depois disso, vale a política normal.

## Segunda camada
`aisef_project.py settings --apply` grava em `.claude/settings.json` as regras nativas `ask`/`deny` equivalentes, mais `disableBypassPermissionsMode` e `DO_NOT_TRACK=1`. Se o hook falhar ou for desligado, essas regras continuam valendo.
