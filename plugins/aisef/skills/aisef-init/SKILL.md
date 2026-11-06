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
O init criou os Agent Contracts do orquestrador e dos 8 agentes do plugin em `.aisef/contracts/agents/*.json`, com `status: "draft"`. Agente em draft e bloqueado pelo gateway. Mostre ao usuario, numa tabela, o teto de cada um (recursos, Git, ambiente maximo; o `validator` so tem Git de leitura) e pergunte se aprova (AskUserQuestion: todos, alguns, nenhum agora). Com o OK:
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

### Grafo de codigo (recomendacao padrao, pergunte antes)
O AISEF recomenda dois grafos que se complementam: **codebase-memory-mcp** (codigo: chamadas, rotas, raio de impacto) e
**Graphify** (docs e decisoes: ADRs, specs, `.aisef/`). Ofereca os dois (em projeto novo ou pequeno, diga que o ganho e
baixo agora; a **aisef-tooling**, secao 6, os oferece de novo quando o codigo crescer). AskUserQuestion (multiSelect): codebase-memory-mcp, Graphify, nenhum agora. Para cada um escolhido
mostre o que faz, o risco (a checagem de versao em segundo plano do codebase-memory-mcp e o envio de docs ao modelo no
Graphify) e o comando de instalacao no escopo do projeto, tudo em `<skill-dir>/../aisef-tooling/SKILL.md` secao 6 e
`references/grafo-de-codigo.md`. **Nao instale sem o OK**; sem resposta, trate como "nenhum agora". Depois de instalar,
proponha liberar em `.aisef/config.json` -> `mcp_allow` so as ferramentas de leitura listadas la (a edicao pede
aprovacao). Nao e requisito para seguir: sem grafo, o AISEF funciona como antes.

## 8. Proximo passo
- Projeto existente: rode **aisef-discovery** no modo "projeto existente".
- Projeto novo: rode **aisef-discovery** no modo "projeto novo".

Explique ao usuario, em duas linhas: o gateway so atua dentro do Claude Code; em outras ferramentas as regras do `AGENTS.md` sao apenas orientacao.
