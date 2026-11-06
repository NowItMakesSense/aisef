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
  - T1: operação destrutiva sobe um nível. Lista ampliada em 2026-11-05: DROP, TRUNCATE, DELETE sem WHERE, ALTER…DROP, rollback de migration, `rm` recursivo, `git clean`, descartar alterações (`checkout --`/`restore`/`stash drop`), apagar branch, force push, remover volumes de container, `kubectl delete` e `terraform destroy`.
  - T2: produção é sempre execução pontual.
  - T3: segredos nunca aparecem em logs.
  - T4: acesso ao schema não implica acesso aos dados.
  - T5: o AISEF funciona sem banco conectado.
- **Autorização de escopo vale no máximo 7 dias** (2026-11-05).
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
- **O validador só usa Git de leitura**, e **um agente só fica `active` com aprovação do usuário** (confirmados em 2026-11-05). O gateway aplica o teto de cada subagente.

## Painel
- JSON como fonte de dados, em **visão derivada** dos contratos e do log. O painel nunca é fonte de verdade.
- Mermaid gera os diagramas.
- **Com a integridade comprometida, o painel continua mostrando os dados**, com o banner vermelho, para permitir a investigação (2026-11-05).

## Plugin (empacotamento, 2026-11-05)
- **Plugin do Claude Code distribuído por marketplace** no GitHub, em vez de uma skill copiada para cada projeto. O código fica no plugin e os dados ficam em `.aisef/` no projeto.
- O AISEF **não absorve** a skill `new-project-setup` (decisão revista pelo usuário em 2026-11-05). Os dois seguem independentes. Os padrões de banco e segredos do gateway, que vieram de lá na v0.1, foram reescritos do zero em `hooks/sensitive_patterns.json`.
- **Execution Gateway por hook PreToolUse.** As aprovações usam o prompt nativo de permissão (`ask`), que o modelo não consegue responder. Nível reforçado sem registro aprovado para a operação exata resulta em `deny`.
- **Banco a partir de uma sessão:** o ambiente alvo é desconhecido, então a política trata como produção. Na prática, fica bloqueado por padrão.
- **Chave privada e head** ficam em `~/.aisef/`, fora do repositório.

## Melhorias pós-análise (2026-11-05)
- **Briefs em vez de JSON escrito à mão** (`aisef_new.py`), para economizar tokens.
- **Caminho rápido** de manutenção (`FEAT-MAINT`) para mudanças pequenas.
- **Regras nativas de segunda camada são `ask`, não `deny`,** para não impedir o que a política permite com aprovação. O gateway passa a registrar no log as tentativas que nega ou leva à aprovação.
- **Log:** checkpoints assinados, segmentos arquivados, rotação de chave (a antiga é aposentada) e âncoras externas.
- **Avaliações das skills:** os casos com shell só rodam em Linux e macOS, porque o Windows não tem sandbox para o Bash.

## Sugestão de ferramentas (2026-11-06)
- **Nova skill `aisef-tooling`**, que roda no fim da discovery e sob demanda. Ela usa fontes prontas em vez de uma busca própria: a skill `find-skills` (skills.sh), o MCP Registry oficial e os marketplaces de plugins.
- **A `find-skills` é oferecida no `aisef-init`, não exigida.** Sem ela, a busca usa `npx skills find` direto.
- **Instalar skill, plugin ou MCP pede aprovação no gateway.** Isso muda o que o agente consegue fazer. A instalação é no escopo do projeto, e o passo de instalação da `find-skills` (`-g -y`) não é usado.
