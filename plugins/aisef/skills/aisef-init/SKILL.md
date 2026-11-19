---
name: aisef-init
description: 'Inicia o AISEF num projeto, novo ou ja existente. Cria .aisef/ (contratos, aprovacoes, autorizacoes, relatorios, blueprints), o log de auditoria assinado com Ed25519 e ativa o Execution Gateway do plugin. Use quando o usuario disser "novo projeto", "iniciar projeto", "setup do projeto", "colocar o AISEF neste projeto", "bootstrap" ou "scaffold", ou quando a skill aisef encontrar um projeto sem .aisef/config.json.'
---

# aisef-init

CORE = `<skill-dir>/../../core`. Python = `$AISEF_PYTHON`, senao `python3`/`python` (precisa da biblioteca `cryptography` para assinar o log; sem ela o log fica so com cadeia de hash e o init avisa).

## 1. Detecte o caso
- Ja existe `.aisef/config.json`: nao reinicie. Rode **aisef-check** e siga com a skill **aisef**.
- O repositorio tem codigo (arquivos-fonte, manifests como `package.json`, `pyproject.toml`, `pom.xml`, migrations, docs): **projeto existente**.
- Pasta vazia ou so com README: **projeto novo**.
- Diga ao usuario qual caso detectou e por que.

## 2. Pergunte so o necessario para criar `.aisef/` (uma pergunta por vez, AskUserQuestion)
| Chave | Pergunta | Notas |
|---|---|---|
| `project_id` | Identificador curto (ex.: `PRJ-LOJA`) | padrao `^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$` |
| `name` | Nome do projeto | |
| `environment` | Esta maquina/sessao trabalha em `dev`, `staging` ou `prod`? | Padrao `dev`. Na duvida, a politica trata como `prod`. |

Reaproveite o que o usuario ja disse. O resto (stack, dominio, requisitos) e assunto da **aisef-discovery**, nao daqui. Em projeto existente, investigue antes de perguntar o nome.

## 3. Crie
```
python -I CORE/aisef_project.py init --project . --project-id <ID> --name "<nome>" --environment <env>
```
Isso cria `.aisef/{contracts/{features,tasks,agents},blueprints,approvals,authorizations,reports,audit,keys}`, `config.json` e o evento genesis. A chave **privada** e o head assinado ficam em `~/.aisef/` (fora do repositorio). Nunca leia nem copie esses arquivos.

Pergunte tambem se o usuario quer **uma branch por feature** (e apagar a branch depois do merge do PR). Se sim, com o OK, acrescente em `config.json` (a edicao pede aprovacao): `"git": {"branch_per_feature": true, "delete_branch_after_merge": true, "branch_prefix": "feat/"}`. Detalhes na skill **aisef**, secao "Branch por feature".

## 4. Ative os agentes (decisao do usuario)
O init criou os Agent Contracts do orquestrador e dos 9 agentes do plugin (inclusive o `implementer`, que faz as fatias verticais) em `.aisef/contracts/agents/*.json`, com `status: "draft"`. Agente em draft e bloqueado pelo gateway. Mostre ao usuario, numa tabela, o teto de cada um (recursos, Git, ambiente maximo; o `validator` so tem Git de leitura) e pergunte se aprova (AskUserQuestion: todos, alguns, nenhum agora). Com o OK:
```
python -I CORE/aisef_project.py agents --project . --activate [--roles backend,qa]
```
O comando abre o prompt nativo de permissao (a decisao e do usuario) e registra a aprovacao no log.

## 5. Segunda camada de protecao (pergunte antes)
O gateway e um hook; se ele falhar ou for desligado, as regras nativas do Claude Code continuam valendo. Mostre o que falta com `python -I CORE/aisef_project.py settings --project .` e, com o OK do usuario, grave com `--apply` (mescla em `.claude/settings.json` sem apagar nada; abre o prompt nativo). As regras incluem `env.DO_NOT_TRACK=1` (desliga a telemetria das CLIs de busca, como `npx skills`; um valor do usuario e respeitado), pedem aprovacao para instalar skill, plugin ou MCP e incluem `disableBypassPermissionsMode`; mesmo sem elas, em modo bypass o gateway nega tudo o que pediria aprovacao. Ferramentas MCP pedem aprovacao ate o usuario libera-las em `.aisef/config.json` -> `"mcp_allow": ["mcp__servidor__ferramenta", "mcp__docs__*"]` (so leitura e o que ele confia). Recomende tambem o sandbox do Claude Code (`/sandbox`): o gateway le comandos por padroes e reduz o risco, mas nao e uma fronteira de seguranca.

## 6. Documente para outras ferramentas (pergunte antes de editar)
Proponha acrescentar `CORE/templates/AGENTS.aisef.md` ao `AGENTS.md` do projeto (crie se nao existir; ferramentas como Codex, Cursor e Gemini leem esse arquivo) e uma linha no `CLAUDE.md`:
```
Este projeto usa o AISEF (plugin aisef): estado em .aisef/, regras em AGENTS.md (secao AISEF).
```
Mostre o texto e so grave com OK. Nunca sobrescreva arquivos existentes em silencio.

## 7. Pesquisa de ferramentas (pergunte antes)
A **aisef-tooling** sugere skills, plugins e MCPs para o projeto e pesquisa skills com a skill `find-skills`
(`vercel-labs/skills`). Se ela ainda nao estiver em `.claude/skills/` nem em `~/.claude/skills/`, ofereca instalar no
projeto (AskUserQuestion). Com o OK:
```
DISABLE_TELEMETRY=1 npx --yes skills add vercel-labs/skills@find-skills -a claude-code -y
```
O gateway abre o prompt nativo. Sem ela, a aisef-tooling usa `npx skills find` direto; nada deixa de funcionar.

### Skills de engenharia do Matt Pocock (recomendacao padrao, pergunte antes)
O fluxo SDD + TDD do AISEF usa as skills que o modelo pode chamar do plugin `mattpocock-skills` (MIT): `grilling`, `domain-modeling`, `tdd`, `codebase-design`, `code-review` e `diagnosing-bugs`. O agente `implementer` ja pre-carrega a `tdd`. Sem o plugin, o AISEF segue regras proprias equivalentes, entao nada deixa de funcionar. Veja se ele ja esta instalado (`claude plugin list --json`). Se nao estiver, ofereca (AskUserQuestion). Com o OK:
```
claude plugin install mattpocock-skills@claude-plugins-official --scope project
```
O gateway abre o prompt nativo. Nao rode o `/setup-matt-pocock-skills` (tracker e labels): no AISEF, spec e fatias ficam em `.aisef/`, nao no issue tracker.

### Grafos: Graphify e padrao, codebase-memory-mcp e opcional (pergunte antes de instalar)
- **Graphify (docs e decisoes: ADRs, specs, `docs/`, `.aisef/`) e padrao desde a 0.11.0.** O `init` ja grava
  `"graphify": {"enabled": true, "backend": "none", "paths": ["docs", ".aisef"]}` no `.aisef/config.json`.
  - `backend: none`: so o passo estrutural, nada enviado a provedor de modelo.
  - Pergunte uma vez (AskUserQuestion), com o Graphify como primeira opcao, marcada "(Recomendado, padrao)":
    instalar e gerar agora, ou desligar.
  - Com o OK: instalacao e geracao da **aisef-tooling, secao 6**, com `GRAPHIFY_BACKEND=none`.
  - Se recusar: grave `"enabled": false` (a edicao do config pede aprovacao); o doctor para de lembrar.
  - Sem resposta, deixe ligado: o doctor lembra no inicio de cada sessao ate o grafo existir ou o usuario desligar.
- **codebase-memory-mcp (codigo: chamadas, rotas, raio de impacto)** continua opcional e em avaliacao (o `metrics`
  compara as tarefas com e sem ele).
  - Ofereca so se o projeto ja tem codigo de tamanho razoavel; em projeto novo ou pequeno, diga que o ganho e baixo agora.
  - Mostre o risco (checagem de versao em segundo plano) e o comando, ambos da aisef-tooling, secao 6.
- **Para os dois:** nao instale sem o OK. Depois de instalar um servidor MCP, proponha liberar em
  `.aisef/config.json` -> `mcp_allow` so as ferramentas de leitura listadas na secao 6 (a edicao pede aprovacao).
  Nenhum dos dois e requisito para seguir.

## 8. Proximo passo
- Projeto existente: rode **aisef-discovery** no modo "projeto existente".
- Projeto novo: rode **aisef-discovery** no modo "projeto novo".

Explique ao usuario, em duas linhas: o gateway so atua dentro do Claude Code; em outras ferramentas as regras do `AGENTS.md` sao apenas orientacao.
