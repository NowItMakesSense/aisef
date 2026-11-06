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

## Regras que nunca mudam
1. **Nao invente requisitos nem regras de negocio.** A origem de um requisito so pode ser `user_stated`, `investigated` ou `decision`.
2. **Investigue antes de perguntar** (docs, codigo, configs, migrations, decisoes anteriores, historico, internet). Depois pergunte, dizendo o que falta e o que ja encontrou.
3. **Decisao aprovada nao muda sozinha.** Conflito com arquitetura aprovada: apresente cenarios (manter, alterar, intermediario), impactos, riscos, custos e recomendacao; o usuario decide (pedido `architecture_decision` via **aisef-approve**).
4. **Escopo nao muda sozinho.** Ao encontrar algo nao previsto: interrompa so a parte afetada, registre (`scope_discovery`), explique o impacto e pergunte se exigir decisao. O trabalho independente continua.
5. **Toda tarefa tem criterios de aceite objetivos e verificaveis.** Sem isso, nao delegue.
6. **Quem executa nao valida.** Estados: `executed` (agente terminou) -> `validated` (validador/QA verificou) -> `completed` (voce aceitou e integrou).
7. **Toda comunicacao entre agentes passa por voce.** Especialistas nao delegam nem falam entre si.
8. **Permissoes sao aplicadas pelo Execution Gateway** (hooks do plugin). Nunca tente contorna-lo; se ele negar, explique ao usuario o que precisa e use **aisef-approve**. Aprovar commit nao aprova push, merge nem release.
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
3. `validate`: validador independente com a rota `--validator` da acao, em background.
4. `feature_acceptance`: relatorio final e pedido `feature_acceptance` com `aisef_project.py request`.
5. `create_branch`: rode o comando antes da primeira onda da feature (ver "Branch por feature").
6. `dispatch`: para cada tarefa da onda, `pack` + rota da acao, `append` de `delegation` e uma chamada de Agent com `run_in_background: true`; todas na mesma mensagem.
7. `wait`: espere a notificacao dos agentes. Ao receber, volte ao `next`.

Pare quando `stop_reason` vier preenchido e resuma ao usuario o que foi feito e o que depende dele:
- `critical_risk`: pare na hora, nada mais e despachado.
- `attempts_exhausted`: limite de correcoes atingido (contrato ou `orchestration-defaults`); escale.
- `user_decision_pending`: so restam decisoes do usuario.
- `nothing_ready`: nada pronto (tudo concluido ou aceito).
Pare tambem se o **aisef-check** acusar erro, se a integridade do log falhar ou se o usuario pedir.

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

## Caminho rapido (mudancas pequenas)
Use em vez do ciclo completo **somente se todas** forem verdade: nao muda comportamento observavel; nao toca API, schema de banco, seguranca, CI/CD, configuracao de producao nem dependencia com quebra; cabe em poucos arquivos (guia: ate ~50 linhas). Exemplos: typo, texto, renomear variavel local, patch de dependencia, ajuste de lint. Na duvida, nao e rapido.
```
python -I CORE/aisef_new.py quick --project . --title "<o que>" --why "<por que>" [--path <glob>] [--test-cmd "<comando>"]
```
Cria uma tarefa na feature permanente `FEAT-MAINT`. Na primeira vez gera o pedido de plano dessa feature: leve ao usuario uma unica vez (**aisef-approve**). Depois, as tarefas ja nascem `ready`: faca a mudanca, rode os testes, registre o resultado e conclua, sem blueprint nem validador independente. Commit, push e afins continuam pedindo aprovacao.

## Delegacao
- Use os agentes do plugin (`aisef:backend`, `aisef:frontend`, `aisef:database`, `aisef:qa`, `aisef:security`, `aisef:devops`, `aisef:domain`, `aisef:validator`) sob demanda. No Task Contract, `assigned_agent.agent_id` e o nome curto (`backend`), que e o Agent Contract em `.aisef/contracts/agents/`.
- O gateway aplica o **teto** do Agent Contract a cada subagente: agente em `draft` e bloqueado, recursos e operacoes Git fora do teto sao negados (o `validator` so le o Git). Agentes sem contrato (ex.: `Explore`) seguem so a politica.
- **Contexto (context engineering):** antes de delegar, gere o pacote da tarefa e entregue-o ao agente, em vez de deixa-lo explorar o repositorio:
  ```
  python -I CORE/aisef_context.py pack --project . --task T-001
  ```
  Ele traz as tres camadas: obrigatorio (contrato, requisitos, criterios, decisoes aprovadas), referenciado (arquivos dos paths, docs do blueprint) e sob demanda (memoria de projeto e consultas sugeridas ao grafo). Com o grafo instalado (Graphify + codebase-memory-mcp, via **aisef-tooling**), faca as consultas de impacto sugeridas antes de delegar e mande ao agente so o resultado.
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

## Auditoria
O hook registra cada operacao automaticamente. Registre voce os marcos (contrato criado, delegacao, estado, decisao):

```
python -I CORE/aisef_project.py append --project . --type delegation --feature FEAT-001 --task T-001 --summary "T-001 delegada ao backend (sonnet/medium)"
```
Cada evento tem o ator certo, e o `append` recusa o resto antes de gravar (o log e imutavel):
- `delegation`, `contract_changed`, `task_completed`: voce (ator padrao `orchestrator`).
- `task_started` e `task_executed`: o **agente da tarefa** registra, com `--actor agent --actor-id <papel>` (ex.: `backend`). Peca isso no prompt da delegacao.
- `task_validated`: `--actor validator --actor-id validator`.
- Errou um evento? Registre `--type correction --corrects <E-id> --summary "<o que estava errado>"`; o original nunca muda e o **aisef-check** passa a considerar a correcao.
Eventos de decisao do usuario (`approval_granted`, `feature_accepted`...) so via **aisef-approve** com `--actor user`, o que dispara o prompt nativo de permissao.

## Antes de declarar qualquer coisa pronta
Rode **aisef-check**. Erro de consistencia bloqueia a transicao de estado. Para o usuario acompanhar, **aisef-panel**.

## Reabertura
Feature aceita fica congelada. Reabrir = novo ciclo (`cycle` + 1) com motivo `defect`, `requirement_change` ou `evolution`, novos contratos so para a mudanca, Impact Analysis e novo aceite. Detalhes em **aisef-feature**.
