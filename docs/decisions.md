# Decisões registradas

Decisões tomadas pelo usuário na conversa "Continuação de projeto com GPT" (claude.ai), que transformou o [contexto arquitetural](aisef-context.md) nos artefatos de `plugins/aisef/core/`. A seção "Plugin" no fim reúne as decisões tomadas ao empacotar o projeto.

## Feature e ciclo de vida
- **Reabertura de feature = novo ciclo**, nunca edição do antigo. A entrega, as evidências e a aprovação anteriores ficam congeladas. O motivo é classificado como `defect`, `requirement_change` ou `evolution`.
- **Estados da tarefa:** `executed` (agente terminou), `validated` (critérios verificados) e `completed` (orquestrador aceitou). Também existem `draft`, `ready`, `in_progress`, `blocked`, `rejected` e `cancelled`.
- **Subtarefa** usa o mesmo schema do Task Contract, com `kind: "subtask"` e `parent_task_id`.
- **Limites de tentativas (padrão A):** 3 correções automáticas, 1 consulta a especialista, depois escala ao usuário. Uma tarefa pode reduzir esses limites; aumentá-los exige aprovação do usuário.
- **`executed` no Execution Report** significa apenas que o agente terminou. Quem promove a tarefa é o validador e o orquestrador.

## Permissões (matriz)
- **Produção:** execução só com **aprovação reforçada**, em casos pontuais. É de uso único, vale no máximo 30 minutos e exige diff, rollback e justificativa. Nunca é concedida por escopo.
- **Config, CI e IaC:** aprovação por escopo em dev e staging. Em produção, aprovação reforçada (opção A da segunda rodada).
- **Arquivos sensíveis em produção:** aprovação reforçada, coerente com a regra de produção.
- **DML em staging depende da classificação do dataset:**

  | Dataset | Escrita | Leitura de linhas |
  |---|---|---|
  | Sintético | por escopo | por escopo |
  | Anonimizado e verificado | por escopo | por operação |
  | Anonimizado sem verificação, ou real | tratado como produção | tratado como produção |

- **Leitura de `repo_code` e `db_schema` em produção:** aprovação por operação (opção B), em vez de escopo somente leitura.
- **Git:** status, log e diff são livres. Commit, push, merge e release exigem, cada um, sua própria aprovação. Force push, reescrita de histórico e exclusão de branch exigem aprovação reforçada.
- **Regras transversais:**
  - T1: operação destrutiva sobe um nível.
  - T2: produção é sempre execução pontual.
  - T3: segredos nunca aparecem em logs.
  - T4: acesso ao schema não implica acesso aos dados.
  - T5: o AISEF funciona sem banco conectado.
- Em conflito, vale a regra **mais restritiva**. Recurso ou ambiente não classificado é tratado como sensível ou como produção.

## Auditoria
- **Assinatura Ed25519 por evento** (opção A), com um head assinado. Quem verifica conhece só as chaves públicas.
- O head precisa ficar **fora** do armazenamento do log.
- A ancoragem externa do head (opção B) fica como reforço futuro.

## Agentes
- Toda comunicação passa pelo orquestrador.
- O agente não altera escopo, decisões nem contratos, mas pode contestar com evidências.
- O agente não valida o próprio trabalho.
- A memória pertence ao projeto.
- O Agent Contract define só um **teto** de permissão. A permissão efetiva vem da política e da autorização.

## Painel
- JSON como fonte de dados, em **visão derivada** dos contratos e do log. O painel nunca é fonte de verdade.
- Mermaid gera os diagramas.

## Plugin (empacotamento, 2026-11-05)
- **Plugin do Claude Code distribuído por marketplace** no GitHub, em vez de uma skill copiada para cada projeto. O código fica no plugin e os dados ficam em `.aisef/` no projeto.
- O AISEF **absorve** a skill `new-project-setup`. Na v0.1, os padrões de bloqueio de banco e segredos e a ideia da entrevista já migraram.
- **Execution Gateway por hook PreToolUse.** As aprovações usam o prompt nativo de permissão (`ask`), que o modelo não consegue responder. Nível reforçado sem registro aprovado para a operação exata resulta em `deny`.
- **Banco a partir de uma sessão:** o ambiente alvo é desconhecido, então a política trata como produção. Na prática, fica bloqueado por padrão, o que é coerente com a regra anterior do `new-project-setup`.
- **Chave privada e head** ficam em `~/.aisef/`, fora do repositório.
