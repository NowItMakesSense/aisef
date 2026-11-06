---
name: aisef-feature
description: 'Especifica uma feature no AISEF - Feature Contract (requisitos versionados, regras de negocio, escopo, RTM), Engineering Blueprint (arquitetura, endpoints, telas, entidades, migracoes, ameacas, DevOps, testes) e Task Contracts com criterios de aceite verificaveis, todos validados pelos JSON Schemas do plugin. Tambem trata reabertura de feature aceita como novo ciclo. Use quando o usuario pedir uma feature nova, mudanca de requisito, correcao de defeito numa feature aceita, ou "especificar", "quebrar em tarefas", "blueprint".'
---

# aisef-feature

CORE = `<skill-dir>/../../core`. **Nunca escreva os contratos JSON inteiros a mao**: escreva um *brief* curto e deixe o gerador expandir, validar contra os schemas e gravar. Ajustes depois sao Edits pequenos nos arquivos gerados.

## 1. Feature Contract + Tasks (um comando)
Base: `.aisef/discovery.md`. Faltou algo? Volte a **aisef-discovery**; nunca preencha com suposicao.
Veja o formato com `python -I CORE/aisef_new.py example feature`, escreva o brief num arquivo temporario fora de `.aisef/` e rode:
```
python -I CORE/aisef_new.py feature --project . --brief <brief.json>
```
Gera `contracts/features/FEAT-*.json`, um `contracts/tasks/T-*.json` por tarefa, a RTM, os criterios e o pedido `plan_approval` (pendente). Se o brief tiver erro, nada e gravado e a mensagem diz o que corrigir.
- Requisito: `origin` so pode ser `user_stated` (padrao), `investigated` ou `decision`. Nunca invente.
- Toda tarefa tem criterios **objetivos e verificaveis** e ao menos um requisito; todo requisito tem tarefa.
- `role` da tarefa = agente do plugin (`backend`, `frontend`, `database`, `qa`, `security`, `devops`, `domain`); `paths` = arquivos que ele pode alterar; `depends_on` e `parallelizable` controlam o paralelismo.
- Tarefa que precisa de `db_data`: inclua `resources` e, no Task Contract gerado, a classificacao do dataset.
Depois, leve o plano ao usuario com **aisef-approve** (`decide` aprovado ja marca o contrato como `approved_for_execution` e as tarefas como `ready`).

## 2. Engineering Blueprint (um comando)
Depois do plano aprovado. `python -I CORE/aisef_new.py example blueprint` mostra o brief (componentes, endpoints, entidades com flags `pk`/`pii`/`secret`/`fk:ENT.campo`, migracoes com rollback, ameacas, niveis de teste). Rode:
```
python -I CORE/aisef_new.py blueprint --project . --brief <brief.json>
```
O gerador ja inclui 401 em endpoint autenticado e marca migracoes como reversiveis. **Todo elemento aponta para requisitos.** ADR so vale com aprovacao do usuario (`architecture_decision` via **aisef-approve**).

## 3. Subtarefas e ajustes
Subtarefa: copie o Task Contract, troque `task_id`, `kind: "subtask"` e `parent_task_id` (Edit pequeno). Voce pode cria-las sem nova aprovacao desde que respeitem escopo e decisoes.

## 4. Valide sempre
Depois de qualquer ajuste manual, rode **aisef-check**. Os geradores ja registram o evento `contract_created`.

## Versionamento
Contratos e schemas tem versao explicita. Tarefa em andamento nunca e migrada em silencio para uma versao nova do contrato: a mudanca e registrada (`contract_changed`) e validada.

## Reabertura de feature aceita
A entrega, as evidencias e a aprovacao anteriores ficam congeladas. Crie um novo ciclo (`cycle` + 1) ligado ao anterior, com o motivo:
- `defect`: a entrega nao cumpria um requisito aprovado. Prioridade alta; registre falha de validacao no ciclo anterior.
- `requirement_change`: comportamento novo desejado. Segue o fluxo de alteracao de requisitos (nova versao).
- `evolution`: melhoria sem mudar requisitos. Trate como feature nova dependente da antiga.
Exija Impact Analysis (o que da versao anterior pode regredir?), contratos e tarefas so para a mudanca e novo aceite comparando com o ciclo anterior. Registre `feature_reopened`.
