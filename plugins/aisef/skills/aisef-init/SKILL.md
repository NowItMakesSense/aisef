---
name: aisef-init
description: 'Inicia o AISEF num projeto, novo ou ja existente. Cria .aisef/ (contratos, aprovacoes, autorizacoes, relatorios, blueprints), o log de auditoria assinado com Ed25519 e ativa o Execution Gateway do plugin. Use quando o usuario disser "novo projeto", "iniciar projeto", "setup do projeto", "colocar o AISEF neste projeto", "bootstrap" ou "scaffold", ou quando a skill aisef encontrar um projeto sem .aisef/config.json.'
---

# aisef-init

CORE = `<skill-dir>/../../core`. Python = `$AISEF_PYTHON`, senao `python3`/`python` (precisa das bibliotecas `jsonschema` e `cryptography`; sem a `cryptography` o init **recusa** e diz o comando exato: o `AISEF_PYTHON` de outro Python que ja as tenha, ou o `pip install` no Python dos hooks. Repasse ao usuario e rode o init de novo).

## 1. Detecte o caso
- Ja existe `.aisef/config.json`: nao reinicie. Rode a skill **aisef-check** (o script e `CORE/check_project.py --project .aisef --policy CORE/permission-policy.v0.1.json --defaults CORE/orchestration-defaults.v0.1.json`; sem `--policy` aparece o aviso POLICY-SKIPPED) e siga com a skill **aisef**.
- O repositorio tem codigo (arquivos-fonte, manifests como `package.json`, `pyproject.toml`, `pom.xml`, migrations, docs): **projeto existente**.
- Pasta vazia ou so com README: **projeto novo**.
- Diga ao usuario qual caso detectou e por que.

## 2. Pergunte so o necessario para criar `.aisef/` (uma pergunta por vez, AskUserQuestion)
| Chave | Pergunta | Notas |
|---|---|---|
| `project_id` | Identificador curto (ex.: `PRJ-LOJA`) | padrao `^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$` |
| `name` | Nome do projeto | |
| `environment` | Esta maquina/sessao trabalha em `dev`, `staging` ou `prod`? | Padrao `dev`. Na duvida, a politica trata como `prod`. |
| `profile` | Quanta cerimonia? `solo` (Recomendado: a triagem escolhe entre caminho rapido, enxuto e completo), `team` (ciclo completo por padrao) ou `regulated` (sem caminho rapido; TDD sempre; blueprint em risco alto) | Padrao `solo`. O gateway e o log assinado sao iguais nos tres. Mudar depois e editar `profile` no `config.json` (o gateway pede a sua aprovacao). |

Reaproveite o que o usuario ja disse. O resto (stack, dominio, requisitos) e assunto da **aisef-discovery**, nao daqui. Em projeto existente, investigue antes de perguntar o nome.

## 3. Crie
```
python -I CORE/aisef_project.py init --project . --project-id <ID> --name "<nome>" --environment <env> --profile <perfil>
```
Isso cria `.aisef/{contracts/{features,tasks,agents},blueprints,approvals,authorizations,reports,audit,keys}`, `config.json` e o evento genesis. A chave **privada** e o head assinado ficam em `~/.aisef/` (fora do repositorio). Nunca leia nem copie esses arquivos.

Pergunte tambem se o usuario quer **uma branch por feature** (e apagar a branch depois do merge do PR). Se sim, com o OK, acrescente em `config.json` (a edicao pede aprovacao): `"git": {"branch_per_feature": true, "delete_branch_after_merge": true, "branch_prefix": "feat/"}`. Detalhes na skill **aisef**, secao "Branch por feature".

**Repositorio Git e GitHub (antes de qualquer commit ou push).** Confira sem rede:
```
git rev-parse --git-dir
git remote get-url origin
```
- Sem repositorio: com o OK do usuario, `git init -b main` (o doctor e o `next` avisam enquanto isso faltar).
- Sem remote: **nao suponha que o repositorio nao existe**. Pergunte ao usuario se o projeto ja tem repositorio no GitHub e qual (dono e nome), e confira com `gh repo view <dono>/<nome> --json nameWithOwner,url`.
  - Existe: `git remote add origin <url>`.
  - Nao existe: proponha `gh repo create <nome> --private --source . --remote origin` (publico so se ele pedir).
  Ligar ou criar o repositorio e decisao do usuario: o gateway pergunta (`remote_config`). Sem remote, nenhum push funciona; o `next` mostra a acao `setup_remote` ate isso ser resolvido.

## 3b. Projeto existente: detecte stack e arquitetura
```
python -I CORE/aisef_project.py detect --project .
```
Grava `.aisef/architecture.json` (stacks, estilos com confianca e evidencia, violacoes da regra de dependencia, praticas e recomendacoes) e cria os drafts dos agentes da stack detectada (revisor e corretor de build da linguagem). Mostre o resumo ao usuario dizendo que e **heuristica**; confirmar o estilo e adota-lo fica para a **aisef-discovery**. Em projeto novo, rode o mesmo comando depois que a stack existir.

## 4. Setup em lote (uma decisao do usuario)
O init criou os Agent Contracts do **nucleo** do catalogo (`CORE/agents/catalog.v0.1.json`: papeis `always` sem `tier: extended`) em `.aisef/contracts/agents/*.json`, com `status: "draft"`; o `detect` acrescentou os da stack e, com estilo de arquitetura detectado, o `architecture-reviewer`. Agente em draft e bloqueado pelo gateway, e agente sem contrato nao edita.

Mostre o plano do setup, que junta o que antes eram quatro pedidos:
```
python -I CORE/aisef_setup.py --project .
```
- **agents**: ativar os drafts. Mostre a equipe agrupada por tipo e o teto de cada grupo (recursos, Git, ambiente maximo) (`python -I CORE/aisef_catalog.py list --tier core`):

  - **executores**: implementer, backend, frontend, database, devops;
  - **avaliadores** (so relatam; o roteamento de revisao chama em toda tarefa): code-reviewer, database-reviewer, pr-test-analyzer, security e os revisores da stack;
  - **corretores** (diff minimo): os corretores de build da stack;
  - **consultores**: planner, architect, code-explorer;
  - o `validator`, so com Git de leitura.

  Diga que existe a **equipe estendida** (qa, doc-updater, e2e-runner, code-simplifier, refactor-cleaner, performance-optimizer, spec-miner, docs-lookup, commit-reviewer e outros, `aisef_catalog.py list --tier extended`), que entra quando o usuario pede ou quando o trabalho pedir: `agents --roles doc-updater` cria o draft. Papeis `manual` (React build, saude) tambem so por pedido.
- **settings**: regras nativas de segunda camada em `.claude/settings.json` (mescla, nunca apaga). Se o gateway falhar ou for desligado, elas continuam valendo. Incluem `env.DO_NOT_TRACK=1` (desliga a telemetria das CLIs de busca, como `npx skills`; um valor do usuario e respeitado), pedem aprovacao para instalar skill, plugin ou MCP e incluem `disableBypassPermissionsMode`; mesmo sem elas, em modo bypass o gateway nega tudo o que pediria aprovacao.
- **practices**: boas praticas da stack e do estilo em `.claude/rules/aisef/` (nao sobrescreve arquivo mudado no projeto).
- **sandbox** (so em Linux, macOS e WSL2; o plano nao mostra no Windows nativo): liga `sandbox.enabled` no `.claude/settings.json`. O sandbox isola os comandos; o gateway decide o que pode rodar; o log prova o que rodou. Com ele ligado, o gateway pergunta quando um comando pede para sair do sandbox (`dangerouslyDisableSandbox`). Se o usuario recusar, grave `"sandbox_reminder": false` no `.aisef/config.json` (a edicao pede aprovacao) e o doctor para de lembrar. No Windows nativo, so diga que o sandbox existe no WSL2.
- **docs**: a secao AISEF (`CORE/templates/AGENTS.aisef.md`) no `AGENTS.md`, que Codex, Cursor e Gemini leem, e uma linha no `CLAUDE.md`. Acrescenta, nunca sobrescreve.

Pergunte **uma vez** (AskUserQuestion, `multiSelect: true`, todos marcados como recomendados) o que aplicar. Com a escolha, **um** comando, que abre **um** prompt nativo e registra a decisao no log:
```
python -I CORE/aisef_setup.py --project . --apply --only <itens escolhidos> [--roles <agentes, se ele limitou>]
```

Ferramentas MCP pedem aprovacao ate o usuario confiar nelas. Dois jeitos: por ate 7 dias, renovavel, com `python -I CORE/aisef_mcp.py trust --project . --tool mcp__servidor__ferramenta[,glob]` (decisao do usuario; o proprio prompt do gateway mostra o comando), ou sem prazo em `.aisef/config.json` -> `"mcp_allow"`. Ferramenta que executa codigo ou comandos (execute_*, *_eval, run_*, sql...) nunca entra por glob: so pelo nome exato no `mcp_allow` ou com `--allow-code-execution`.

## 5. Pesquisa de ferramentas (pergunte antes)
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
- **Graphify (docs e decisoes: ADRs, specs, `docs/`, `.aisef/`) e padrao desde a 0.11.0.** Em **projeto existente**, proponha incluir as pastas de codigo em `graphify.paths` (ex.: `["docs", ".aisef", "src"]`): o grafo do codigo alimenta o `pack`, o `code-explorer` e a regra de dependencia. O `init` ja grava
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

## 6. Proximo passo
- Projeto existente: rode **aisef-discovery** no modo "projeto existente".
- Projeto novo: rode **aisef-discovery** no modo "projeto novo".

Explique ao usuario, em duas linhas: o gateway so atua dentro do Claude Code; em outras ferramentas as regras do `AGENTS.md` sao apenas orientacao.
