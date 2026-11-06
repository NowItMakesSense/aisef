# Ciclo de vida AISEF (detalhe)

## Projeto novo
1. **aisef-init** cria `.aisef/` e o log de auditoria.
2. **aisef-discovery** conduz a descoberta (problema, dores, publico, objetivos, escopo, requisitos funcionais e nao funcionais, regras de negocio, excecoes, integracoes, seguranca, dados, UX, testes).
   Ao final, **aisef-tooling** sugere skills, plugins e MCPs ligados ao discovery; so instala o que o usuario escolher.
3. Decisoes de stack e arquitetura sao contextualizadas (modelo de dados, consistencia, operacao, custos, conhecimento da equipe...). Explique o que e, para que serve, quando usar e evitar, pros, contras, custos e alternativas. Arquitetura evolutiva: resolva o necessario agora e registre as decisoes (ADR no blueprint).
4. Para cada feature: Feature Contract -> Blueprint -> Tasks (skill **aisef-feature**).

## Projeto existente
Nao reconstrua nada. Primeiro investigue estrutura, codigo, arquitetura, features existentes, schemas e migrations (sem conectar ao banco), docs, testes, dependencias e decisoes anteriores. Registre em `.aisef/discovery.md` o que encontrou, com a fonte, e o que segue desconhecido. Depois identifique o que realmente precisa mudar.

## Impact Analysis (feature nova em projeto existente)
APIs, telas, componentes, tabelas, modulos, integracoes, dependencias, riscos, compatibilidade e possiveis regressoes. Avalie primeiro se a arquitetura atual comporta a necessidade.

## Planning
Investigacao, especificacao, decisoes, dependencias, tarefas e criterios de aceite. O usuario aprova por fluxo, feature ou requisito, conforme o plano.

## Execution
Implementacao, testes, revisao e documentacao. Contexto progressivo para cada agente:
- **obrigatorio**: Task Contract, requisitos ligados, decisoes aprovadas que afetam a tarefa;
- **referenciado**: caminhos de docs e codigo relevantes (com origem e versao);
- **sob demanda**: o resto, que o agente pede ao orquestrador.

## Modo continuo (loop engineering)
Depois do plano aprovado, o orquestrador conduz sozinho: `next` -> dispatch em paralelo da onda -> validacao independente -> complete -> `next`... ate um criterio de parada. Ele so leva ao usuario o que e do usuario.

**Estado efetivo.** O `aisef_project.py next` combina o estado do Task Contract com o ultimo evento de ciclo de vida no log: `delegation`, `task_started` e `task_resumed` -> em andamento; `task_paused` -> bloqueada; `task_executed` -> executed; `task_validated` -> validated; `task_rejected` -> reprovada (volta para dispatch com `--attempt` + 1); `task_completed` -> completed. `cancelled` e `blocked` no contrato prevalecem. Por isso registre `delegation` ao despachar: sem ele, a tarefa ainda parece pronta e seria despachada de novo.

**Acoes** (`--json` para ler em codigo):

| Acao | Quando | O que fazer |
|---|---|---|
| `dispatch` | tarefas `ready` (ou reprovadas) com dependencias satisfeitas, sem pedido bloqueando e sem conflito de paths com tarefas em andamento; so a onda atual | pack + rota de cada uma, `delegation`, Agent em background, todas na mesma mensagem |
| `validate` | `executed` sem `task_validated` | validador com a rota `--validator --executor-level` da acao |
| `complete` | `validated` sem `task_completed` | aisef-check, contrato `completed`, `append` de `task_completed` |
| `wait` | delegadas ou iniciadas | esperar a notificacao dos agentes |
| `await_decision` | pedido `pending` (com o que ele bloqueia), `scope_discovery` sem pedido registrado depois, intervencao pedida no Execution Report, limite de tentativas, risco critico | aisef-approve; para `scope_discovery`, crie o pedido `scope_change_decision` com `request` |
| `feature_acceptance` | todas as tarefas da feature concluidas e nenhum pedido de aceite do ciclo | relatorio final + pedido `feature_acceptance` |
| `create_branch` / `delete_merged_branch` | opcao `git` do config (ver SKILL) | rodar o comando / pedir cada exclusao reforcada |
| `idle` | nada a fazer | encerrar |

**Criterios de parada (`stop_reason`).** `critical_risk` para na hora, mesmo com trabalho pronto (intervencao `critical_risk_operation` ou risco `critical` no relatorio mais recente de uma tarefa aberta). `attempts_exhausted` (reprovacoes acima de `limits.max_fix_attempts` ou de `orchestration-defaults`) e `user_decision_pending` so param quando nao resta trabalho automatizavel: o trabalho independente continua. `nothing_ready` quando nada mais esta pronto. Enquanto houver agente em voo, `stop_reason` fica vazio e a acao e `wait`.

**Com o `/loop`.** Modo autoritmado: cada iteracao chama `next` e executa as acoes; subagentes em background acordam a sessao ao terminar; sem agente em voo e com espera, um `ScheduleWakeup` longo e o fallback. Com `stop_reason`, o loop termina com um resumo para o usuario. O loop nunca decide: aprovacoes, aceite e operacoes Git continuam com o usuario, pelo prompt nativo.

## Branch por feature
Opcao `git` em `.aisef/config.json` (o **aisef-check** valida em `CONFIG-GIT`): `branch_per_feature` cria `prefixo + id da feature sem FEAT-` ao iniciar a execucao; `delete_branch_after_merge` apaga a branch remota e a local depois do merge confirmado do PR. Cada exclusao e uma operacao Git reforcada propria (pedido `git_operation`/`branch_delete` + autorizacao reforcada com a `operation` exata); o `next` mostra, por comando, se ja existe pedido e o status dele.

## Priorizacao
Dependencias, bloqueios, impacto na entrega, risco tecnico e prioridade do usuario. Voce pode reorganizar a fila tecnica, nunca a prioridade de negocio sem autorizacao.

## Retomada apos interrupcao
Recupere o estado (contratos, relatorios, log), identifique tarefas interrompidas, verifique alteracoes parciais (`git status`/`git diff`), revalide permissoes e dependencias e retome do ultimo ponto seguro. Operacoes nao idempotentes exigem reconciliacao antes de repetir.

## Feature Acceptance
O encerramento exige: requisitos rastreados, criterios verificados, testes de integracao e regressao executados, documentacao atualizada, ausencia de pendencias ocultas, seguranca e permissoes verificadas e relatorio final planejado x executado (atendidos, nao atendidos, arquivos, testes, evidencias, decisoes, riscos, pendencias). O aceite **nao** autoriza commit, push, merge nem release.

## Arena (segunda opiniao)
Quando houver conflito ou decisao importante, ou o usuario pedir: rode um debate (defensor da solucao atual, challenger, especialista de dominio, revisor independente) com subagentes separados e entregue relatorio com argumentos, evidencias, alternativas, riscos, incertezas e recomendacao. Nao e votacao; a palavra final e do usuario.
