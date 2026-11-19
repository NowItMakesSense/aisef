# Regras do aisef-check

Gerado por `tools/gen_docs.py` a partir de `core/check_project.py` e `core/check_knowledge.py`. Não edite à mão.

**150 regras** em 26 grupos. Erro bloqueia a transição de estado; aviso não bloqueia.

## Projeto (`PROJECT-*`)

A pasta tem documentos AISEF para checar.

`PROJECT-EMPTY`

## Identificadores (`ID-*`)

Ids unicos e nomes de arquivo coerentes.

`ID-DUP`, `ID-FILE`

## Política (`POLICY-*`)

A política de permissões é válida.

`POLICY-SCHEMA`, `POLICY-SKIPPED`

## Permissões (`PERM-*`)

Recursos e escopos das tarefas respeitam a política.

`PERM-DENIED`, `PERM-POLICY-VERSION`, `PERM-PROD-SCOPE`, `PERM-SCOPE-REQUIRED`

## Agentes (`AGENT-*`)

Agent Contracts ativos, papel, teto de recursos e de ambiente.

`AGENT-ENV`, `AGENT-INACTIVE`, `AGENT-PATH-CEILING`, `AGENT-RESOURCE`, `AGENT-ROLE`, `AGENT-ROLE-UNKNOWN`, `AGENT-UNKNOWN`, `AGENT-VERSION`

## Feature Contract (`FEAT-*`)

Requisitos, critérios e arquitetura da feature.

`FEAT-ARCH-UNKNOWN`, `FEAT-CRITERION-REQ`, `FEAT-REQ-NO-CRITERION`

## Plano de tarefas (`PLAN-*`)

Plano coerente com a feature e os papéis.

`PLAN-DEPS`, `PLAN-FEATURE`, `PLAN-FEATURE-VERSION`, `PLAN-ORPHAN-TASK`, `PLAN-ROLE`, `PLAN-TASK-MISSING`, `PLAN-VERSION`

## Task Contracts (`TASK-*`)

Requisitos e critérios ligados, sem ciclos.

`TASK-CRITERION-REQ`, `TASK-CYCLE`, `TASK-FEATURE`, `TASK-REQ-SUPERSEDED`, `TASK-REQ-UNKNOWN`, `TASK-REQ-VERSION`

## Dependências (`DEP-*`)

Dependências existem e não formam ciclo.

`DEP-CROSS-FEATURE`, `DEP-CYCLE`, `DEP-UNKNOWN`

## Paralelismo (`PAR-*`)

Tarefas paralelas não disputam arquivos.

`PAR-FILE-CONFLICT`, `PAR-PATH-OVERLAP`

## Rastreabilidade (RTM) (`RTM-*`)

Requisito → tarefa → critério sem buracos.

`RTM-CRITERION-UNKNOWN`, `RTM-DUP`, `RTM-MISSING`, `RTM-REQ-SUPERSEDED`, `RTM-REQ-UNKNOWN`, `RTM-RULE-UNKNOWN`, `RTM-TASK-MISSING`, `RTM-TASK-NOT-IN-RTM`, `RTM-TASK-NOT-LINKED`, `RTM-VERSION`

## Requisitos (`REQ-*`)

Histórico de versões dos requisitos.

`REQ-HISTORY`

## Engineering Blueprint (`BP-*`)

Todo elemento aponta para requisitos aprovados.

`BP-ADR-UNAPPROVED`, `BP-APPROVAL-REF`, `BP-BEFORE-PLAN`, `BP-COMPONENT-UNKNOWN`, `BP-ENDPOINT-UNKNOWN`, `BP-ENTITY-UNKNOWN`, `BP-FEATURE`, `BP-FEATURE-VERSION`, `BP-FIELD-UNKNOWN`, `BP-MULTIPLE-ACTIVE`, `BP-NO-PK`, `BP-REQ-SUPERSEDED`, `BP-REQ-UNCOVERED`, `BP-REQ-UNKNOWN`, `BP-REQ-UNTESTED`

## Execution Reports (`REPORT-*`)

Relatório do agente coerente com a tarefa e com evidências.

`REPORT-AGENT`, `REPORT-ATTEMPTS`, `REPORT-CONSULTATIONS`, `REPORT-CRITERIA-MISSING`, `REPORT-CRITERIA-REQUIRED`, `REPORT-CRITERIA-UNKNOWN`, `REPORT-EVIDENCE-UNKNOWN`, `REPORT-FILE-OUT-OF-SCOPE`, `REPORT-TASK`, `REPORT-VERSION`

## Spec (`SPEC-*`)

Fatias verticais pedem spec com seams de teste aprovados.

`SPEC-REQUIRED`, `SPEC-SEAM-UNKNOWN`

## Fatias verticais (`SLICE-*`)

Toda fatia tem ao menos um criterio verificado por teste automatizado.

`SLICE-NO-AUTOMATED-TEST`

## TDD (`TDD-*`)

Evidencia de teste vermelho antes do verde, no relatorio do executor.

`TDD-EVIDENCE-MISSING`, `TDD-GREEN-FAILING`, `TDD-RED-BEFORE-GREEN`, `TDD-RED-NOT-FAILING`

## Autoridade de design (`DESIGN-*`)

Tokens de design validos, aprovados como decisao arquitetural, e UI coberta por eles.

`DESIGN-MISSING`, `DESIGN-SCHEMA`, `DESIGN-UNAPPROVED`

## Validação (`VAL-*`)

Validação independente, nunca do próprio executor.

`VAL-NO-VALIDATOR`, `VAL-SELF-ATTEST`

## Roteamento (`ROUTE-*`)

Validador não roda abaixo do nível do executor.

`ROUTE-VALIDATOR-WEAKER`

## Estado x evidência (`STATE-*`)

Cada estado tem o evento e o relatório que o sustentam.

`STATE-CLOSED-NO-ACCEPT`, `STATE-DEP-INCOMPLETE`, `STATE-FEATURE-TASKS`, `STATE-NO-COMPLETE-EVENT`, `STATE-NO-EXEC-EVENT`, `STATE-NO-REPORT`, `STATE-NO-START-EVENT`, `STATE-NO-VALIDATION`, `STATE-PLAN-NO-EVENT`, `STATE-REPORT-STATUS`, `STATE-UNAPPROVED-PLAN`

## Approval Center (`APPROVAL-*`)

Pedidos, decisões e eventos consistentes.

`APPROVAL-AUTH-MISMATCH`, `APPROVAL-AUTH-MISSING`, `APPROVAL-BLOCKED-TASK`, `APPROVAL-DECIDER`, `APPROVAL-EVENT-FEATURE`, `APPROVAL-EVENT-REF`, `APPROVAL-EVENT-TYPE`, `APPROVAL-EXPIRED-PENDING`, `APPROVAL-FEATURE`, `APPROVAL-ORDER`, `APPROVAL-TASK`

## Autorizações (`AUTH-*`)

Escopo e reforçada válidas, no prazo e na operação certa.

`AUTH-CYCLE`, `AUTH-DATASET`, `AUTH-ENV`, `AUTH-EXPIRED`, `AUTH-FEATURE`, `AUTH-HISTORY`, `AUTH-MISSING`, `AUTH-NOT-SCOPABLE`, `AUTH-POLICY-VERSION`, `AUTH-REDUNDANT`, `AUTH-REINFORCED-EXPIRED`, `AUTH-REINFORCED-VALIDITY`, `AUTH-RESOURCE`, `AUTH-SCOPE-TOO-LONG`, `AUTH-STATUS`, `AUTH-TASK`

## Log de auditoria (`LOG-*`)

Atores, ordem e referências dos eventos.

`LOG-CORRECTION-ORDER`, `LOG-CORRECTION-UNKNOWN`, `LOG-PROJECT`, `LOG-SUBJECT`, `LOG-TASK-ACTOR`, `LOG-TIME-ORDER`, `LOG-UNKNOWN-AGENT`, `LOG-UNKNOWN-FEATURE`, `LOG-UNKNOWN-TASK`, `LOG-VALIDATOR-ROLE`

## Configuração (`CONFIG-*`)

Opções do config.json.

`CONFIG-GIT`, `CONFIG-GRAPHIFY`

## Memória de projeto (`KNW-*`)

Entradas de .aisef/knowledge com fonte e sem segredos.

`KNW-FEATURE-MISSING`, `KNW-FILENAME`, `KNW-ID-DUP`, `KNW-ID-NAME`, `KNW-JSON`, `KNW-LESSON-EVIDENCE`, `KNW-LINK`, `KNW-SCHEMA`, `KNW-SECRET`, `KNW-SOURCE-DECISION-UNKNOWN`, `KNW-SOURCE-FILE-MISSING`, `KNW-SOURCE-TASK-MISSING`, `KNW-TASK-MISSING`
