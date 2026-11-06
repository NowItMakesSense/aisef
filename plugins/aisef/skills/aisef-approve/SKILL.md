---
name: aisef-approve
description: 'Approval Center do AISEF - leva ao usuario cada decisao que so ele pode tomar (aprovacao de plano, autorizacao de escopo, operacao, aprovacao reforcada, operacao Git, decisao arquitetural, mudanca de escopo, aceite de feature), mostrando impacto, diff, testes, rollback e riscos, e registra a decisao com auditoria. Use quando o Execution Gateway negar ou pedir aprovacao, quando um plano/blueprint/ADR precisar de OK, ou quando o usuario disser "aprovar", "autorizar", "aceitar a feature", "o que esta pendente".'
---

# aisef-approve

CORE = `<skill-dir>/../../core`. Schemas: `approval-request.schema.v0.1.json` (o pedido) e `authorization.schema.v0.1.json` (o que um escopo ou uma aprovacao reforcada gera). Exemplos validos: gere o demo (`python -I CORE/make_demo_project.py <tmp>/demo`) e veja `approvals/` e `authorizations/`.

**Voce nunca decide.** So o usuario decide; o registro da decisao passa pelo prompt nativo de permissao do Claude Code, que voce nao consegue responder.

## 1. Monte o pedido -> `.aisef/approvals/APR-NNN.json` com `status: "pending"`
Um pedido por decisao (`request_type`):
- `plan_approval`, `scope_authorization`, `operation_approval`, `reinforced_approval`, `git_operation`, `architecture_decision`, `scope_change_decision`, `feature_acceptance`.
- **Git: um pedido por operacao.** Aprovar commit nao cobre push, merge nem release.
- `presented`: arquivos afetados, `diff_ref`, testes, impacto, rollback, justificativa, requisitos e evidencias. **Nunca valores de segredo**, so o nome do recurso.
- `blocks`: o que fica bloqueado e se o trabalho independente continua.
- `architecture_decision`: pelo menos 2 opcoes com impactos e riscos, mais recomendacao fundamentada.
- `reinforced_approval` (producao, destrutivos em staging, force push, reescrita de historico, apagar branch): diff ou plano exato, impacto, rollback, justificativa, risco medio ou maior, validade de no maximo 30 minutos, uso unico, e a `operation` **exata** (o comando literal que sera executado).
Valide com **aisef-check** antes de mostrar. Criar o pedido pendente nao abre prompt; alterar um pedido existente abre.

## 2. Apresente ao usuario (AskUserQuestion)
Resuma em linguagem direta o que sera feito, por que, o impacto, o rollback e os riscos, citando o arquivo do pedido. Opcoes: aprovar, recusar, pedir mudancas (e, em decisao arquitetural, uma opcao por alternativa). Em reforcadas e operacoes Git destrutivas, peca as tres confirmacoes: impacto lido, rollback lido, diff revisado.

## 3. Registre a decisao (um unico comando, abre o prompt nativo)
Para escopo ou reforcada aprovados, escreva antes o rascunho da autorizacao num arquivo temporario fora de `.aisef/` (mesmo formato do demo, sem `status`/`granted_*`).
```
python -I CORE/aisef_project.py decide --project . --request APR-NNN --choice approve \
    [--option OPT-A] [--note "..."] [--ack impact_read,rollback_read,diff_reviewed] [--authorization <rascunho.json>]
```
O comando valida tudo contra os schemas antes de gravar, gera a autorizacao (escopo `active` ou reforcada `approved`), anexa `approval_granted`/`approval_rejected` e `authorization_granted` com ator `user`, e preenche `audit.decided_event_ref`. Pedido decidido nao muda: para mudar, crie outro pedido.

## 4. Depois
- Escopo ativo: o gateway libera as operacoes cobertas (recurso + ambiente + validade) sem novo prompt.
- Reforcada: repita **exatamente** a `operation` aprovada. O gateway ainda pede a confirmacao nativa uma vez.
- `feature_acceptance` aprovado: a feature fecha, mas commit, push, merge e release continuam pedindo aprovacao propria.
- Para listar pendencias: arquivos em `.aisef/approvals/` com `status: "pending"` (ou a aba Aprovacoes do **aisef-panel**).
