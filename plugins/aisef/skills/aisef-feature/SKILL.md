---
name: aisef-feature
description: 'Especifica uma feature no AISEF em fases - Grill (entrevista ate fechar cada ramo), Spec (solucao, historias, seams de teste), Fatias verticais (tracer bullets com blocking edges) e o Engineering Blueprint - gerando Feature Contract, Task Contracts com TDD e RTM validados pelos JSON Schemas do plugin. Tambem trata reabertura de feature aceita como novo ciclo. Use quando o usuario pedir uma feature nova, quiser "fazer uma spec", "especificar", "quebrar em tarefas/tickets/fatias", "blueprint", mudar requisito ou corrigir defeito numa feature aceita, ou citar /to-spec, /to-tickets ou /grill-me num projeto com .aisef/.'
---

# aisef-feature

CORE = `<skill-dir>/../../core`. Método: o do Matt Pocock (grill → spec → tickets → TDD), com a rastreabilidade do AISEF. Detalhes e modelos em `references/spec-and-slices.md`.

**Nunca escreva os contratos JSON inteiros à mão.** Escreva um *brief* curto e deixe o gerador expandir, validar contra os schemas e gravar. Ajustes depois são Edits pequenos nos arquivos gerados.

**Sempre diga ao usuário em que fase ele está e qual é a próxima**, por exemplo: "Estamos no Grill (1/4). Depois: Spec → Fatias → aprovação." Se ele citar `/to-spec`, `/to-tickets` ou `/grill-me`, explique que são comandos que só ele pode digitar e que esta skill faz o mesmo papel: Spec e Fatias, gravadas em `.aisef/` em vez do issue tracker.

Base: `.aisef/discovery.md`. Faltou algo? Volte à **aisef-discovery**; nunca preencha com suposição.

## Fase 0: Triagem (o código escolhe o caminho)
Antes do Grill, estruture o pedido e rode a triagem. Investigue o código para estimar caminhos, arquivos e linhas; não chute.
```
python -I CORE/aisef_triage.py --project . --paths <globs> --changes <tipos> --files N --lines N [--slices N] [--risk low|medium|high] --json
```
Tipos de mudança: `behavior`, `bugfix`, `ui`, `refactor` (normais); `typo`, `text`, `docs`, `lint`, `rename_local`, `dependency_patch`, `config_local`, `test_only` (sem comportamento); `api`, `schema`, `security`, `ci`, `infra`, `dependency_breaking`, `public_contract`, `cross_module` (sempre full).

Diga ao usuário em uma linha o que saiu ("Caminho: lean, porque ..."). Ele pode **subir** o caminho (`--force full`); descer não existe. Depois:
- **quick**: caminho rápido da skill **aisef** (`aisef_new.py quick`), sem estas fases.
- **lean**: Grill curto (só os ramos que faltam), Spec curta (`solution`, uma história, `test_seams` confirmados), **uma** fatia com TDD, **sem blueprint**. Ponha a saída `--json` da triagem em `"triage"` no brief: o gerador fixa o `code-reviewer` como único revisor e recusa mais de uma fatia. O validador independente continua.
- **full**: as fases abaixo, completas. Também vale pôr a triagem em `"triage"`, para o contrato guardar o motivo.

## Fase 1: Grill (entender antes de escrever)
Entreviste o usuário **uma pergunta por vez**, até fechar cada ramo da ideia: comportamento esperado, exceções, limites, o que fica fora. Antes de cada pergunta, investigue o que dá para descobrir sozinho.
- Use a skill `grilling` do plugin `mattpocock-skills`, se estiver instalada. Para vocabulário do domínio, use a `domain-modeling` (`GLOSSARY.md` e ADRs).
- Sem o plugin, siga o mesmo método: pergunta direta, uma de cada vez, com a sua recomendação.
- Pule o Grill só se a conversa já fechou todos os ramos. Nesse caso, diga isso ao usuário.

## Fase 2: Spec
Escreva a seção `spec` do brief:
- `solution`: a solução, em uma ou duas frases;
- `user_stories`: "Como <quem>, quero <o quê>, para <por quê>";
- `implementation_decisions`: decisões de implementação, sem caminhos de arquivo nem código;
- `testing_decisions`: decisões de teste;
- `test_seams`: **os seams de teste**, isto é, as interfaces públicas onde os testes vão atuar.

**Confirme os seams com o usuário antes de seguir** (AskUserQuestion). Prefira os seams existentes e os mais altos possíveis; o ideal é um. Os requisitos (`requirements`) só podem ter origem `user_stated`, `investigated` ou `decision`.

## Fase 3: Fatias verticais
Quebre a feature em **fatias verticais** (`"kind": "slice"`):
- cada fatia é um caminho completo pelas camadas necessárias (`touches`: `ui`, `api`, `domain`, `data`, `integration`, `infra`, `docs`);
- é demonstrável sozinha;
- cabe numa janela de contexto;
- tem ao menos um critério verificado por teste automatizado nos seus seams.

Regras:
- **Nunca fatie por camada** (uma tarefa de backend e outra de frontend): isso é horizontal, serializa o trabalho e não prova nada sozinho.
- `depends_on` = blocking edges. A primeira fatia é o *tracer bullet*: o caminho mais fino que liga tudo de ponta a ponta.
- Refatoração ampla primeiro ("deixe a mudança fácil, depois faça a mudança fácil"). Se for grande, use expand-contract em vez de fatias.
- Fatias sem conflito de arquivos e sem dependência entre si podem ter `"parallelizable": true`, e vão para a mesma onda.
- O `role` padrão de uma fatia é `implementer`. Use outro papel só quando a fatia for de um único domínio: `devops` para pipeline, `database` para migração pura.

Mostre a lista ao usuário (título, camadas, blocking edges, seams) e ajuste a granularidade com ele antes de gerar. Veja o formato com `python -I CORE/aisef_new.py example feature`, escreva o brief num arquivo temporário fora de `.aisef/` e rode:
```
python -I CORE/aisef_new.py feature --project . --brief <brief.json>
```
O comando gera o Feature Contract com a spec, um Task Contract por fatia (com `tests.tdd_required` e `tests.seams`), a RTM, os critérios e o pedido `plan_approval`. Se algo estiver errado (spec sem seams, seam fora da spec, fatia sem critério), nada é gravado e a mensagem diz o que corrigir.
- `complexity` (`trivial`, `normal` ou `complex`) entra no plano e pesa na escolha de modelo e effort.
- Fatia que precisa de `db_data`: inclua `resources` e, no Task Contract gerado, a classificação do dataset.

Depois, leve o plano ao usuário com **aisef-approve**. O `decide` aprovado marca o contrato como `approved_for_execution` e as fatias como `ready`.

## Fase 4: Engineering Blueprint
Só no caminho **full**. Vem depois do plano aprovado. `python -I CORE/aisef_new.py example blueprint` mostra o brief: componentes, endpoints, entidades com flags `pk`/`pii`/`secret`/`fk:ENT.campo`, migrações com rollback, ameaças e níveis de teste.
```
python -I CORE/aisef_new.py blueprint --project . --brief <brief.json>
```
**Todo elemento aponta para requisitos.** ADR só vale com aprovação do usuário (`architecture_decision` via **aisef-approve**).

## Execução e revisão (o que vem depois)
A execução é o modo contínuo da skill **aisef**: o `implementer` faz cada fatia com TDD (vermelho antes do verde, registrado em `tdd_evidence`), e o validador confere de forma independente. Com todas as fatias concluídas, rode a skill `code-review` do plugin `mattpocock-skills` sobre a feature (padrões + aderência à spec) antes do pedido `feature_acceptance`. Sem o plugin, faça a mesma revisão com um subagente.

## Subtarefas e ajustes
Subtarefa: copie o Task Contract, troque `task_id`, `kind: "subtask"` e `parent_task_id` (Edit pequeno). Pode ser criada sem nova aprovação, desde que respeite escopo e decisões. Depois de qualquer ajuste manual, rode **aisef-check**. Os geradores já registram o evento `contract_created`.

## Versionamento
Contratos e schemas têm versão explícita. Tarefa em andamento nunca é migrada em silêncio para uma versão nova do contrato: a mudança é registrada (`contract_changed`) e validada.

## Reabertura de feature aceita
A entrega, as evidências e a aprovação anteriores ficam congeladas. Crie um novo ciclo (`cycle` + 1) ligado ao anterior, com o motivo:
- `defect`: a entrega não cumpria um requisito aprovado. Prioridade alta; registre a falha de validação no ciclo anterior.
- `requirement_change`: comportamento novo desejado. Segue o fluxo de alteração de requisitos (nova versão).
- `evolution`: melhoria sem mudar requisitos. Trate como feature nova dependente da antiga.

Exija Impact Analysis (o que da versão anterior pode regredir?), contratos e fatias só para a mudança e novo aceite comparando com o ciclo anterior. Registre `feature_reopened`.
