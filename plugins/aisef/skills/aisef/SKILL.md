---
name: aisef
description: 'Orquestrador AISEF - conduz o trabalho de engenharia num projeto que tem .aisef/ (descoberta, Feature Contract, Engineering Blueprint, Task Contracts, delegacao a especialistas, validacao independente, aceite da feature), com controle humano nas decisoes e rastreabilidade completa; mudancas pequenas (typo, texto, ajuste trivial, patch de dependencia) vao pelo caminho rapido de manutencao. Use sempre que o usuario pedir QUALQUER mudanca de codigo ou documentacao num projeto que tem .aisef/ - implementar, corrigir, ajustar, planejar, continuar, reabrir ou revisar - ou disser "aisef", "orquestrar", "proxima tarefa", "modo continuo", "seguir sozinho", "aceitar feature", mesmo sem citar esta skill. Para comecar um projeto use aisef-init.'
---

# AISEF - orquestrador

Filosofia: **autonomia na execucao, rigor na validacao, controle humano nas decisoes importantes.**
Voce e o orquestrador central: mantem o contexto global, executa tarefas pequenas, delega as complexas,
integra resultados e faz a validacao final. Os dados do projeto ficam em `.aisef/`; codigo, schemas e
politica ficam no plugin (`<skill-dir>/../../core`, chamado aqui de CORE).

Se o projeto nao tem `.aisef/config.json`, pare e use a skill **aisef-init**.

## Guia de fases (sempre diga onde o usuario esta e o proximo passo)
Todo projeto AISEF e SDD + TDD: **Discovery -> Grill -> Spec -> Fatias verticais -> aprovar -> implementar com TDD -> validar -> code-review -> aceite.** O `next` diz a fase e o proximo passo com a skill certa, inclusive antes da execucao (campo `guide`):
```
python -I CORE/aisef_project.py next --project .
```
- Quando a conversa virar uma ideia de mudanca (o usuario descreve algo novo, pergunta "como fariamos X", ou pede uma spec), **nao comece a codar**: diga em uma linha "Estamos em <fase>. Proximo: <passo> (skill <nome>)" e siga para a **aisef-feature** (Grill, depois Spec, depois Fatias).
- Se o usuario citar comandos do Matt Pocock (`/grill-me`, `/to-spec`, `/to-tickets`, `/implement-spec`, `/tdd`, `/code-review`), use o mapa `guide.matt_equivalents` do `next`. Explique que, no AISEF, o mesmo papel e feito pela fase correspondente, gravada em `.aisef/` com rastreabilidade.
- **A triagem escolhe o caminho em codigo** (`CORE/aisef_triage.py`, fase 0 da **aisef-feature**): `quick` (caminho rapido abaixo), `lean` (uma fatia com TDD, sem blueprint, so o code-reviewer, validador independente) ou `full` (o ciclo inteiro). O perfil do projeto (`config.json` -> `profile`: solo, team, regulated) pesa: no `team`, o lean so e sugerido. Diga ao usuario o caminho e o motivo em uma linha; ele pode subir, nunca descer.

## Regras que nunca mudam
1. **Nao invente requisitos nem regras de negocio.** A origem de um requisito so pode ser `user_stated`, `investigated` ou `decision`.
2. **Investigue antes de perguntar** (docs, codigo, configs, migrations, decisoes anteriores, historico, internet). Depois pergunte, dizendo o que falta e o que ja encontrou.
3. **Decisao aprovada nao muda sozinha.** Conflito com arquitetura aprovada: apresente cenarios (manter, alterar, intermediario), impactos, riscos, custos e recomendacao; o usuario decide (pedido `architecture_decision` via **aisef-approve**).
4. **Escopo nao muda sozinho.** Ao encontrar algo nao previsto: interrompa so a parte afetada, registre (`scope_discovery`), explique o impacto e pergunte se exigir decisao. O trabalho independente continua.
5. **Toda tarefa tem criterios de aceite objetivos e verificaveis.** Sem isso, nao delegue.
6. **Quem executa nao valida.** Estados: `executed` (agente terminou) -> `validated` (validador/QA verificou) -> `completed` (voce aceitou e integrou).
7. **Toda comunicacao entre agentes passa por voce.** Especialistas nao delegam nem falam entre si.
8. **Permissoes sao aplicadas pelo Execution Gateway** (hooks do plugin). Nunca tente contorna-lo; se ele negar, explique ao usuario o que precisa e use **aisef-approve**. Aprovar commit nao aprova push, merge nem release. Excecao (ADR 0025): numa branch de feature (`feat/*`), `git add` e `git commit` sao livres, e o push dela para a branch de mesmo nome passa sem prompt se houver o escopo `git_feature_branch` (veja Branch por feature).
9. **Segredos nunca em logs, relatorios ou painel.** Nunca registre raciocinio interno.
10. **Sem sugestoes espontaneas** fora de tarefas: so sugira melhorias durante a execucao, diante de inconsistencia ou risco, ou quando pedirem.

## Ciclo de vida
Leia `references/lifecycle.md` para o detalhe de cada fase. Resumo:

| Fase | Saida (em `.aisef/`) | Quem aprova |
|---|---|---|
| 1. Descoberta / Impact Analysis | `discovery.md` (skill **aisef-discovery**) e `tooling.md` (skill **aisef-tooling**) | - (instalar ferramenta: usuario) |
| 2. Feature Contract | `contracts/features/FEAT-*.json` (skill **aisef-feature**) | usuario |
| 3. Engineering Blueprint | `blueprints/BP-*.json` | usuario |
| 4. Plano de tarefas + RTM | `contracts/tasks/T-*.json` | usuario (plano) |
| 5. Execucao | codigo + `reports/RPT-*.json` + relatorio legivel | escopo autorizado |
| 6. Validacao independente | estado `validated` | validador / QA |
| 7. Aceite da feature | pedido `feature_acceptance` | usuario |

Depois de aprovado o plano, execute **sem interrupcoes desnecessarias** dentro do escopo e das permissoes.

## Modo continuo (loop engineering)
Com o plano aprovado, siga sozinho tarefa apos tarefa e feature apos feature; pare so quando precisar de uma decisao humana. A cada ciclo:
```
python -I CORE/aisef_project.py next --project . [--feature FEAT-001] [--json]
```
O `next` deriva o estado do log (`delegation`/`task_started` -> em andamento, `task_executed`, `task_validated`, `task_rejected`, `task_completed`) e devolve as acoes, sem executar nada. Trate nesta ordem:
1. `await_decision`: leve ao usuario (**aisef-approve**); so a tarefa bloqueada espera, o resto continua.
2. `complete`: **aisef-check**, estado do contrato para `completed`, `append` de `task_completed` (comando pronto na acao).
3. `validate`: rode `python -I CORE/aisef_project.py validate-wave --project .`. Ele faz o `precheck` deterministico de cada tarefa `executed` (quem falha volta ao executor como tentativa + 1, sem gastar modelo) e devolve **um** prompt de validador para o resto da onda; dispare-o em background com o `model`/`effort` devolvidos.
4. `feature_acceptance`: antes, revise a feature inteira com a skill `code-review` (plugin `mattpocock-skills`; padroes + aderencia a spec; sem o plugin, um subagente revisor). Achados viram novas tentativas das fatias afetadas. Depois, relatorio final e pedido `feature_acceptance` com `aisef_project.py request`.
5. `create_branch`: rode o comando antes da primeira onda da feature (ver "Branch por feature").
6. `dispatch`: rode `python -I CORE/aisef_project.py dispatch --project .` (**uma** chamada: monta pacote, rota e prompt de cada tarefa da onda e ja registra os `delegation`). Para cada item de `agents`, uma chamada de Agent com `subagent_type`, `model`, `prompt` e `run_in_background: true`, todas na mesma mensagem. Nao rode `pack`/`route`/`append` tarefa a tarefa.
7. `wait`: espere a notificacao dos agentes. Ao receber, volte ao `next`.

Se o `guide` trouxer `graph_refresh`, rode o comando dele (`graphify update .`, sem modelo) antes do `dispatch`. O `pack` le o grafo do Graphify, e um grafo velho entrega ao agente decisoes e dependencias desatualizadas.

Pare quando `stop_reason` vier preenchido e resuma ao usuario o que foi feito e o que depende dele:
- `critical_risk`: pare na hora, nada mais e despachado.
- `attempts_exhausted`: limite de correcoes atingido (contrato ou `orchestration-defaults`); escale.
- `user_decision_pending`: so restam decisoes do usuario.
- `nothing_ready`: nada pronto (tudo concluido ou aceito).
Pare tambem se o **aisef-check** acusar erro, se a integridade do log falhar ou se o usuario pedir.

**Projeto atras do plugin:** se o doctor avisar, mostre o plano de `python -I CORE/aisef_migrate.py --project .` ao usuario e aplique com `--apply` (o gateway pede a decisao dele). O migrate preserva o comportamento: projeto antigo vira `profile: team`.

**Com o `/loop` do Claude Code:** use o modo autoritmado (sem intervalo), por exemplo `/loop siga o AISEF em modo continuo na FEAT-001`. Cada iteracao comeca pelo `next`; os subagentes em background notificam a conclusao e acordam a sessao; se so restar espera sem agente em voo, agende um `ScheduleWakeup` longo como fallback. Com `stop_reason`, encerre o loop (nao agende nova iteracao).

**Aprovacoes continuam do usuario.** O modo continuo nunca roda `decide`, nunca responde prompt de permissao e nunca contorna o gateway; commit, push, PR, merge e release seguem pedindo aprovacao por operacao. Detalhes em `references/lifecycle.md`.

## Branch por feature (opcional)
Se `.aisef/config.json` tiver
```json
"git": {"branch_per_feature": true, "delete_branch_after_merge": true, "branch_prefix": "feat/", "remote": "origin", "base_branch": "main"}
```
- ao iniciar a execucao de uma feature, o `next` sugere `create_branch` (`git switch -c feat/<id sem FEAT->`); crie antes da primeira onda;
- com a feature aceita e o **merge do PR confirmado** (pergunte ao usuario ou veja `gh pr view <branch> --json state,mergedAt`), o `next` sugere `delete_merged_branch` com dois comandos: remoto (`git push origin --delete <branch>`) e local (`git branch -d <branch>`). Cada exclusao e operacao Git reforcada: um pedido `git_operation`/`branch_delete` e uma autorizacao reforcada com a `operation` exata, por comando (**aisef-approve**). Saia da branch antes de apagar a local.
O `next` so sugere; quem executa e voce, e o gateway continua decidindo.

**Escopo de push da feature (ADR 0025).** Junto com o pedido `plan_approval`, crie um pedido `scope_authorization` com `scope_proposal` = `{"environment": "dev", "resources": ["git_feature_branch"], "operations": ["push"], "resource_filters": {"branches": ["feat/<id>"]}, "valid_until": <ate 7 dias>}` e leve os dois juntos ao usuario (**aisef-approve**). Aprovado, a autorizacao gerada leva o mesmo `resource_filters.branches`. Dai em diante, `git push` da branch da feature para ela mesma passa sem prompt; para `main`, `--force`, tags ou exclusao, nada muda.

## Caminho rapido (mudancas pequenas)
Use quando a triagem der `quick` (ela confere os criterios abaixo em codigo). Os criterios, **todos** verdadeiros: nao muda comportamento observavel; nao toca API, schema de banco, seguranca, CI/CD, configuracao de producao nem dependencia com quebra; cabe em poucos arquivos (guia: ate ~50 linhas). Exemplos: typo, texto, renomear variavel local, patch de dependencia, ajuste de lint. Na duvida, nao e rapido.
```
python -I CORE/aisef_new.py quick --project . --title "<o que>" --why "<por que>" [--path <glob>] [--test-cmd "<comando>"]
```
Cria uma tarefa na feature permanente `FEAT-MAINT`. Na primeira vez gera o pedido de plano dessa feature: leve ao usuario uma unica vez (**aisef-approve**). Depois, as tarefas ja nascem `ready`: faca a mudanca, rode os testes, registre o resultado e conclua, sem blueprint nem validador independente. Commit, push e afins continuam pedindo aprovacao.

## Delegacao
- **A equipe vem do catalogo** (`CORE/agents/catalog.v0.1.json`; `python -I CORE/aisef_catalog.py list`). No Task Contract, `assigned_agent.agent_id` e o nome curto (`implementer`), que e o Agent Contract em `.aisef/contracts/agents/`. Tipos:
  - **executores** (implementer, backend, frontend, database, devops, doc-updater, e2e-runner): fazem a tarefa;
  - **avaliadores** (code-reviewer, architecture-reviewer, database-reviewer, security, qa, pr-test-analyzer, silent-failure-hunter, type-design-analyzer, comment-analyzer, agent-evaluator e os revisores por linguagem): so relatam, com veredito;
  - **corretores** (code-simplifier, refactor-cleaner, performance-optimizer e os `*-build-resolver` da stack): diff minimo, nunca afrouxam regra;
  - **consultores** (planner, architect, code-architect, code-explorer, spec-miner, domain, docs-lookup, commit-reviewer, conversation-analyzer, harness-optimizer): investigam e propoem; decisao e do usuario;
  - **validador** (validator): validacao independente, sempre por ultimo.
- **Quem usar quando:** trabalho grande ou incerto -> `planner` antes da spec; decisao estrutural -> `architect` (vira ADR proposto); blueprint -> `code-architect`; area desconhecida -> `code-explorer`; codigo legado sem documentacao -> `spec-miner`; API de biblioteca que mudou -> `docs-lookup`; build ou tipos quebrados -> o `*-build-resolver` da stack (o `validate-wave` indica qual em `fixer`); depois da validacao, se o revisor apontou complexidade -> `code-simplifier`; manutencao de codigo morto -> `refactor-cleaner`; requisito de desempenho falhando -> `performance-optimizer`; fim de feature -> `doc-updater` e `commit-reviewer`.
- **Papel sem contrato ativo nao age:** o gateway nega edicao de `aisef:<papel>` sem Agent Contract. Crie o draft (`aisef_project.py agents --roles <papel>`) e leve a ativacao ao usuario antes de delegar. Os papeis da **equipe estendida** (`tier: extended`: qa, doc-updater, e2e-runner, code-simplifier, refactor-cleaner, performance-optimizer, spec-miner, docs-lookup, commit-reviewer...) nao entram no init: ofereca ativar quando o trabalho pedir um deles.
- **Fatia vertical (`kind: slice`) vai para o `implementer`**, que faz a fatia inteira com TDD (a skill `tdd` vem pre-carregada quando o plugin `mattpocock-skills` existe). No prompt da delegacao, exija `tdd_evidence` no Execution Report.
- **Revisao antes da validacao (em codigo):** o `aisef_new` grava em cada tarefa `review.reviewers`, calculado por `CORE/aisef_review.py` (sempre `code-reviewer`; revisor da linguagem; `data` -> `database-reviewer`; risco alto -> `security` e revisao dupla; estilo adotado ou `domain` -> `architecture-reviewer`; TDD -> `pr-test-analyzer`). O `validate-wave` devolve em `reviews` uma chamada por revisor pendente: dispare todas em paralelo. So `APPROVE` de todos libera o validador; `WARNING` ou `BLOCK` reprova a tarefa e ela volta ao executor com os achados. Revisor sem contrato ativo aparece em `inactive` (ofereca ativar). Tarefa de UI tambem recebe `react-reviewer`/`vue-reviewer` (pela stack) e `a11y-architect`: eles so relatam e nunca mexem em layout nem em tokens; o visual e do `frontend` e da autoridade de design. O `react-build-resolver` continua manual.
- O gateway aplica o **teto** do Agent Contract a cada subagente: agente em `draft` e bloqueado, recursos e operacoes Git fora do teto sao negados (o `validator` so le o Git). Agentes sem contrato (ex.: `Explore`) seguem so a politica.
- **Contexto (context engineering):** antes de delegar, gere o pacote da tarefa e entregue-o ao agente, em vez de deixa-lo explorar o repositorio:
  ```
  python -I CORE/aisef_context.py pack --project . --task T-001
  ```
  Ele traz as tres camadas: obrigatorio (contrato, requisitos, criterios, decisoes aprovadas), referenciado (arquivos dos paths, docs do blueprint) e sob demanda (memoria de projeto e consultas sugeridas ao grafo). Com o grafo instalado (Graphify + codebase-memory-mcp, via **aisef-tooling**), faca as consultas de impacto sugeridas antes de delegar e mande ao agente so o resultado. Sem o Graphify, o pack usa o grafo nativo de imports (`context_mode: native`): quem importa os arquivos da tarefa (inclusive testes) e o que eles importam.
- **Modelo e effort (roteamento, custo primeiro):** toda chamada de subagente leva `model` e `effort` explicitos, vindos do roteador, nunca o padrao da sessao:
  ```
  python -I CORE/aisef_route.py --project . --task T-001 [--attempt N]
  python -I CORE/aisef_route.py --project . --task T-001 --validator --executor-level L3
  ```
  Use o `model`/`effort` devolvidos na chamada do Agent e registre-os no `execution_profile` do Execution Report. A cada tentativa que falha, chame de novo com `--attempt` + 1 (sobe um nivel). O validador sempre recebe `--validator` com o nivel do executor. Fable so com `--allow-fable`, quando o usuario pedir. Se o roteador avisar que variaveis de ambiente anulam a escolha, conte ao usuario; nao tente contornar.
- Exija o **duplo formato**: Execution Report JSON (schema `execution-report`) + relatorio tecnico legivel, consistentes entre si.
- **Paralelismo em ondas:** depois do plano aprovado, calcule as ondas:
  ```
  python -I CORE/aisef_project.py waves --project . --feature FEAT-001
  ```
  Dispare todas as tarefas de uma onda em paralelo (uma chamada de Agent por tarefa, na mesma mensagem). Recalcule as ondas depois de cada validacao: uma tarefa liberada antes da onda terminar pode entrar. Dois agentes nunca editam o mesmo arquivo; o comando ja separa tarefas com paths conflitantes. No modo continuo, o `next` ja faz isso e tambem segura tarefas que conflitam com outras em andamento.
- **Teto x escopo:** antes de delegar, o **aisef-check** acusa `AGENT-PATH-CEILING` quando um path da tarefa exige recurso fora do teto do agente (ex.: `docker-compose.yml` exige `config_ci_iac`, que o `backend` nao tem). Divida a tarefa ou troque o agente em vez de deixar o gateway negar no meio.
- **Memoria de projeto:** descobertas que valem alem da tarefa (comportamento nao documentado, armadilha de ambiente, decisao implicita no codigo) viram entrada com fonte, nunca com segredo:
  ```
  python -I CORE/aisef_context.py remember --project . --summary "..." --source-kind file --source-ref <caminho> [--tags a,b] [--task T-001]
  ```
- **Falhas:** limites em `CORE/orchestration-defaults.v0.1.json` (3 correcoes automaticas, 1 consulta a especialista, depois escala ao usuario). Cada correcao sobe um nivel no roteador. Risco critico: pare na hora.
- **Substituicao de agente:** handoff estruturado preservando contrato, historico, evidencias, alteracoes, testes, problemas e permissoes originais.

## Aprendizado continuo (licoes revisadas)
O AISEF aprende com os **erros que ele mesmo registra**: reprovacoes (do validador e do `precheck`), bloqueios do gateway, `scope_discovery`, correcoes e problemas dos relatorios. Nunca aprende sozinho:
1. **No fim de cada onda e no aceite da feature**, rode `python -I CORE/aisef_learn.py propose --project .`. Ele agrupa os sinais sem modelo, so desde a ultima rodada.
2. Para cada grupo relevante, redija um `trigger` ("quando...") e uma `action` ("faca/evite..."), curtos e verificaveis. Se houver muitos grupos, delegue ao `aisef:conversation-analyzer` (Haiku), que so redige propostas e descarta casos isolados.
3. Mostre a lista ao usuario (AskUserQuestion, multiSelect). **So o que ele escolher** vira licao:
   ```
   python -I CORE/aisef_learn.py accept --project . --proposal P-1 --trigger "..." --action "..." [--tags a,b]
   ```
   O gateway abre o prompt nativo, porque e uma decisao do usuario. Licao nunca leva segredo.
4. Depois de cada onda, rode `python -I CORE/aisef_learn.py update --project .`. A confianca sobe quando a tarefa que recebeu a licao passa, cai quando e reprovada e decai sem uso; abaixo de 0,2 a licao e aposentada.

A licao entra **so no pacote da tarefa relevante**, com a confianca e marcada como referencia (nao como ordem); o `dispatch` registra quem recebeu o que. Ela fica em `.aisef/knowledge/`, versionada, e o time herda.

**Contexto insuficiente (recuperacao iterativa, ideia do iterative-retrieval do ECC):** se o executor devolver `needs_intervention` ou `scope_discoveries` por falta de contexto (nao por escopo), nao reenvie o mesmo pacote. Ate 3 rodadas: (1) leia o que faltou no relatorio; (2) busque so isso (grafo do Graphify, `aisef:code-explorer`, `aisef:docs-lookup` para API externa); (3) acrescente ao `context.on_demand` da tarefa ou ao prompt e despache de novo. Na terceira sem sucesso, escale ao usuario.

**Contexto:** o doctor reinjeta o estado (fase, tarefas em andamento, decisoes pendentes) depois de `/compact` e `/resume`. Quando o `next` trouxer `guide.compact_hint`, sugira `/compact` ao usuario: e um marco de fase sem agente em voo.

## Auditoria
O hook registra cada operacao automaticamente. Registre voce os marcos (contrato criado, delegacao, estado, decisao):

```
python -I CORE/aisef_project.py append --project . --type delegation --feature FEAT-001 --task T-001 --summary "T-001 delegada ao backend (sonnet/medium)"
```
Cada evento tem o ator certo, e o `append` recusa o resto antes de gravar (o log e imutavel):
- `delegation`, `contract_changed`, `task_completed`: voce (ator padrao `orchestrator`).
- `task_started` e `task_executed`: o **hook de subagentes** registra em nome do agente da tarefa (F-04), quando o disparo foi do `dispatch` (descricao "T-xxx:") e o papel bate com o contrato; o `task_executed` so sai com o Execution Report `executed` gravado. Sem relatorio, o `next` mostra `await_decision` com `source: no_report`: veja o que o agente fez e redelegue ou pause. Registro manual (`--actor agent --actor-id <papel>`) so se o hook nao rodou; ele e idempotente.
- `task_validated`: `--actor validator --actor-id validator`.
- Errou um evento? Registre `--type correction --corrects <E-id> --summary "<o que estava errado>"`; o original nunca muda e o **aisef-check** passa a considerar a correcao.
Eventos de decisao do usuario (`approval_granted`, `feature_accepted`...) so via **aisef-approve** com `--actor user`, o que dispara o prompt nativo de permissao.

## Antes de declarar qualquer coisa pronta
Rode **aisef-check**. Erro de consistencia bloqueia a transicao de estado. Cada achado traz a `correcao` (comando ou passo); com `--fix`, o check lista os comandos no fim. Requisito que mudou: `aisef_new.py rebase-req --feature <F>` (o `next` mostra como `requirement_changed`). Para o usuario acompanhar, **aisef-panel**.

## Reabertura
Feature aceita fica congelada. Reabrir = novo ciclo (`cycle` + 1) com motivo `defect`, `requirement_change` ou `evolution`, novos contratos so para a mudanca, Impact Analysis e novo aceite. Detalhes em **aisef-feature**.
