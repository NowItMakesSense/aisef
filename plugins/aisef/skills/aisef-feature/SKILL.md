---
name: aisef-feature
description: 'Especifica uma feature no AISEF - Feature Contract (requisitos versionados, regras de negocio, escopo, RTM), Engineering Blueprint (arquitetura, endpoints, telas, entidades, migracoes, ameacas, DevOps, testes) e Task Contracts com criterios de aceite verificaveis, todos validados pelos JSON Schemas do plugin. Tambem trata reabertura de feature aceita como novo ciclo. Use quando o usuario pedir uma feature nova, mudanca de requisito, correcao de defeito numa feature aceita, ou "especificar", "quebrar em tarefas", "blueprint".'
---

# aisef-feature

CORE = `<skill-dir>/../../core`. Os schemas em CORE sao a fonte da verdade da forma de cada documento:
`feature-contract.schema.v0.1.json`, `engineering-blueprint.schema.v0.1.json`, `task-contract.schema.v0.1.json`.
Para ver documentos completos e validos de exemplo, gere o demo numa pasta temporaria:
`python -I CORE/make_demo_project.py <tmp>/demo` (veja `contracts/`, `blueprints/`, `authorizations/`).

## 1. Feature Contract -> `.aisef/contracts/features/FEAT-NNN.json`
- Base: `.aisef/discovery.md`. Faltou algo? Volte a **aisef-discovery**; nunca preencha com suposicao.
- Requisitos com `origin` `user_stated` | `investigated` | `decision`, cada um com historico. **Requisito nunca e sobrescrito nem apagado**: mudanca gera nova versao com conteudo anterior, autor, justificativa, data, impactos, aprovacao e tarefas afetadas.
- `business_priority.set_by` e sempre `"user"`.
- Escopo incluido e excluido explicitos. RTM: todo requisito aponta para tarefa(s) e criterio(s).
- Estado inicial de proposta; apresente ao usuario e peca `plan_approval` via **aisef-approve**.

## 2. Engineering Blueprint -> `.aisef/blueprints/BP-NNN.json`
Escrito depois do Feature Contract aprovado e antes das tarefas. Cobre componentes e interacoes, ADRs, endpoints, telas, entidades/campos/migracoes, ameacas com mitigacao, ambientes de deploy e niveis de teste. **Todo elemento aponta para os requisitos que o justificam.** Regras que o schema impoe: endpoint autenticado preve 401/403; migracao tem rollback (destrutiva tambem reversivel); producao exige estrategia de deploy; segredos marcados para nunca irem a log ou painel. ADR so vale com aprovacao do usuario (`architecture_decision`).

## 3. Task Contracts -> `.aisef/contracts/tasks/T-NNN.json`
Cada tarefa: objetivo, agente atribuido, requisitos, escopo (arquivos/recursos), contexto (obrigatorio, referenciado, sob demanda), permissoes (teto; a efetiva vem da politica e da autorizacao de escopo), **criterios de aceite objetivos e verificaveis**, validacao (validador independente quando exigido), entregaveis, risco, limites (`max_fix_attempts: null` = padrao do projeto) e escalonamento. Subtarefa usa o mesmo schema com `kind: "subtask"` e `parent_task_id`; voce pode cria-las sem nova aprovacao desde que respeitem escopo e decisoes.
Se a tarefa precisa de `db_data`, declare a classificacao do dataset (`synthetic`, `anonymized_verified`, `anonymized_unverified_or_real`).

## 4. Valide sempre
Depois de escrever ou alterar qualquer documento, rode **aisef-check**. Corrija erros antes de pedir aprovacao. Registre o marco:
```
python -I CORE/aisef_project.py append --project . --type contract_created --feature FEAT-NNN --summary "Feature Contract FEAT-NNN v1 criado"
```

## Versionamento
Contratos e schemas tem versao explicita. Tarefa em andamento nunca e migrada em silencio para uma versao nova do contrato: a mudanca e registrada (`contract_changed`) e validada.

## Reabertura de feature aceita
A entrega, as evidencias e a aprovacao anteriores ficam congeladas. Crie um novo ciclo (`cycle` + 1) ligado ao anterior, com o motivo:
- `defect`: a entrega nao cumpria um requisito aprovado. Prioridade alta; registre falha de validacao no ciclo anterior.
- `requirement_change`: comportamento novo desejado. Segue o fluxo de alteracao de requisitos (nova versao).
- `evolution`: melhoria sem mudar requisitos. Trate como feature nova dependente da antiga.
Exija Impact Analysis (o que da versao anterior pode regredir?), contratos e tarefas so para a mudanca e novo aceite comparando com o ciclo anterior. Registre `feature_reopened`.
