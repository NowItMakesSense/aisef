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

## 4. Ative os agentes (decisao do usuario)
O init criou os Agent Contracts dos 8 agentes do plugin em `.aisef/contracts/agents/*.json`, com `status: "draft"`. Agente em draft e bloqueado pelo gateway. Mostre ao usuario, numa tabela, o teto de cada um (recursos, Git, ambiente maximo; o `validator` so tem Git de leitura) e pergunte se aprova (AskUserQuestion: todos, alguns, nenhum agora). Com o OK:
```
python -I CORE/aisef_project.py agents --project . --activate [--roles backend,qa]
```
O comando abre o prompt nativo de permissao (a decisao e do usuario) e registra a aprovacao no log.

## 5. Documente para outras ferramentas (pergunte antes de editar)
Proponha acrescentar ao `CLAUDE.md` (e ao `AGENTS.md`, se existir) uma secao curta:
```
## AISEF
Este projeto usa o AISEF (plugin aisef). Estado em .aisef/. Use /aisef para trabalhar em features.
Commit, push, merge, release, arquivos sensiveis e banco passam pelo Execution Gateway.
```
Mostre o texto e so grave com OK. Nunca sobrescreva arquivos existentes em silencio.

## 6. Proximo passo
- Projeto existente: rode **aisef-discovery** no modo "projeto existente".
- Projeto novo: rode **aisef-discovery** no modo "projeto novo".

Explique ao usuario, em duas linhas: o gateway so atua dentro do Claude Code; em outras ferramentas as regras do `AGENTS.md` sao apenas orientacao.
