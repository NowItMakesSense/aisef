# Changelog

## 0.5.0 - 2026-11-06
- **Modo contínuo (`aisef_project.py next`, `core/aisef_next.py`):**
  - Calcula as próximas ações a partir dos contratos, aprovações, relatórios e do log: `dispatch` (onda atual, com os comandos de rota e de pack), `validate`, `complete`, `wait`, `await_decision`, `feature_acceptance`, `create_branch`, `delete_merged_branch` e `idle`. Não executa nada.
  - O estado efetivo vem do contrato combinado com o último evento do log (`delegation`/`task_started` → em andamento, `task_rejected` → retrabalho com `--attempt` + 1).
  - Tarefas bloqueadas por pedido pendente, por `scope_discovery` sem pedido ou por intervenção pedida no relatório ficam fora da onda; o resto continua. Tarefas que conflitam com outra em andamento também esperam.
  - `stop_reason`: `critical_risk` (para na hora), `attempts_exhausted` e `user_decision_pending` (só quando não resta trabalho automatizável), `nothing_ready`.
  - A skill `aisef` e o `lifecycle.md` ganham a seção "Modo contínuo", com o ciclo, os critérios de parada e o uso com o `/loop` autoritmado. As aprovações continuam do usuário.
- **Branch por feature (opcional):** `config.json` → `git` (`branch_per_feature`, `delete_branch_after_merge`, `branch_prefix`, `remote`, `base_branch`). O `next` sugere criar a branch ao iniciar a feature e, com a feature aceita e o merge do PR confirmado, apagar a remota e a local, cada uma com pedido e aprovação reforçada próprios. O `aisef-check` valida a opção (`CONFIG-GIT`) e a `aisef-init` pergunta se o usuário quer usá-la.
- **Correções vindas do uso real:**
  - **Pull request é operação Git:** `pull_request` entra no schema do Approval Center, no teto do Agent Contract (orquestrador) e na política (aprovação por operação). O gateway passa a pedir aprovação para `gh pr create` (antes passava livre) e há regra nativa de segunda camada. O `check_policy_consistency` agora acusa operação Git da política sem tipo correspondente no Approval Center, e vice-versa.
  - **`decide` não aprova reforçada sem autorização reforçada:** aprovar `reinforced_approval` ou `git_operation` de `force_push`, `history_rewrite` ou `branch_delete` exige `--authorization` com `kind: "reinforced"` e a mesma `operation` exata (e mesma feature e tarefa). Antes, gerava um pedido aprovado que o gateway continuava negando.
  - **Prefixo `cd` no gateway:** `cd <raiz do projeto> &&` ou `cd <raiz do projeto>;` (inclusive `/c/...` do Git Bash e `cd .`) é ignorado ao comparar com a operação exata aprovada. `cd` para outro diretório ou comando extra continua negado.
  - **Teto do agente x escopo da tarefa:** nova regra `AGENT-PATH-CEILING` no `check_project`. Cada path de `paths_allowed`/`exclusive_files` é classificado com a mesma função do gateway (`write_resource`) e comparado com `permission_ceiling.resources`; erro para tarefa aberta, aviso para concluída.
  - **`aisef_project.py request`:** valida o rascunho, anexa `approval_requested` e grava o pedido já com `audit.requested_event_ref`. Recusa pedido decidido, de outro projeto ou com id existente, sem gravar nada.
- **Demo com relógio fixo:** o escopo e o pedido pendente do demo vencem em 2026-11-06 14:00 (-03:00); o `run_tests.py` e o passo a passo passam `--now` ao `check_project` do demo.

## 0.4.0 - 2026-11-06
- **Modelo e effort por tarefa (`aisef_route.py`, `core/model-policy.v0.1.json`):**
  - Seleção híbrida, com custo primeiro. Cada papel tem um padrão, e os agentes ganham `model` e `effort` no frontmatter.
  - Sinais do Task Contract sobem um nível na escada L0 (haiku/low) a L6 (opus/high): risco alto, recursos sensíveis (segurança, schema, CI/CD, deploy), `complexity: complex` e mais de 10 paths. `complexity: trivial` desce um nível.
  - Cada tentativa que falha sobe um nível. Fable só com `--allow-fable`.
  - O validador roda no menor nível que seja pelo menos o do executor e use outro modelo.
  - O roteador avisa quando variáveis de ambiente anulam a escolha.
  - O Task Contract ganha `complexity`, e o Execution Report ganha `execution_profile`.
  - O `aisef-check` acusa `ROUTE-VALIDATOR-WEAKER`.
- **Ondas automáticas (`aisef_project.py waves`):**
  - Calcula ondas de tarefas prontas a partir de dependências, `parallelizable`, paths sem conflito e recursos compartilhados. Na dúvida, trata como conflito.
  - O painel mostra as ondas na aba de dependências.
- **Context engineering (`aisef_context.py`):**
  - `pack` monta o pacote da tarefa em três camadas: obrigatório, referenciado e sob demanda.
  - `remember` grava a memória de projeto em `.aisef/knowledge/`, com fonte e recusando segredos. O `aisef-check` valida as entradas.
  - O hook consultivo `graph_nudge` lembra de consultar o grafo antes de Grep/Glob. Ele nunca bloqueia e falha aberto.
- **Grafo de código:**
  - A `aisef-tooling` e a `aisef-init` recomendam o codebase-memory-mcp (código) e o Graphify (docs e decisões), com instalação no escopo do projeto e só as ferramentas de leitura em `mcp_allow`.
  - Riscos verificados: o README e o SECURITY.md do codebase-memory divergem sobre a checagem de versão.
- **Log: correções e ator certo:**
  - `append` recusa, antes de gravar, `task_started`/`task_executed` que não sejam do agente da tarefa e ator `agent`/`validator` sem `--actor-id`.
  - Novo `--corrects` para eventos `correction`.
  - O `aisef-check` rebaixa a aviso o erro de ator de um evento corrigido. A autovalidação nunca é perdoada.
  - O exemplo da skill `aisef` induzia o erro e foi corrigido.

## 0.3.0 - 2026-11-06
- **Sugestão de ferramentas (`aisef-tooling`):** no fim da discovery ou quando você pedir, sugere skills (via `find-skills`/skills.sh), servidores MCP (MCP Registry oficial, API v0.1) e plugins (`claude plugin list --available`). Cada sugestão é ligada a um item do discovery, verificada (fonte, sinais, risco) e gravada em `.aisef/tooling.md`. Só instala o que você escolher, no escopo do projeto.
- **`aisef-init`** oferece instalar a skill `find-skills`.
- **Gateway:** instalar skill, plugin, marketplace ou servidor MCP (`npx skills add`, `claude plugin install`, `claude plugin marketplace add`, `claude mcp add`) pede aprovação; escrever em `.mcp.json` ou `.claude/{skills,agents,commands}/` também. Buscar segue livre.
- **Regras nativas** (`settings --apply`): as mesmas instalações pedem aprovação na segunda camada, e `env.DO_NOT_TRACK=1` desliga a telemetria das CLIs de busca, sem sobrescrever um valor que você já tenha definido.
- **Avaliações:** `tooling-choice` (trigger) e `tooling-suggest` (shell).
- **Bibliotecas na pasta de usuário do pip:** sem permissão de escrita no Python do sistema (comum no Windows), o `pip install` grava em `%APPDATA%\Python`, que o `python -I` dos hooks ignorava; o doctor seguia dizendo que faltavam `jsonschema` e `cryptography`. O novo `core/userlibs.py` acrescenta essa pasta ao fim do `sys.path`, sem precedência sobre a biblioteca padrão nem sobre o plugin.

## 0.2.0 - 2026-11-06
- **Ferramentas MCP e WebFetch no gateway:** ferramentas MCP fora de `mcp_allow` pedem aprovação (e são negadas a subagentes fora do teto); uma URL do WebFetch que carrega token é negada; a auditoria registra chamadas MCP só com os nomes dos campos.
- **Modo bypass:** com `bypassPermissions`, o que pediria aprovação é negado. As regras nativas geradas incluem `disableBypassPermissionsMode`.
- **Agentes de fonte única:** `tools/gen_agents.py` gera `agents/*.md` a partir de um bloco comum de regras e das ferramentas de `AGENT_PROFILES`, as mesmas dos Agent Contracts. A checagem de sincronia roda no `run_tests.py`.
- **Mermaid fora do repositório:** o arquivo de 2,5 MB saiu do Git. Agora ele é baixado uma vez, com versão fixa e conferência por SHA-256, para `~/.aisef/vendor/`. Um download adulterado é recusado.
- **Geradores por brief e caminho rápido:** `aisef_new.py feature`, `blueprint` e `quick`. Quando você aprova o plano, isso passa para o Feature Contract.
- **Gateway:**
  - pede aprovação para código ofuscado ou baixado;
  - registra no log as tentativas que nega ou leva à aprovação;
  - instala regras nativas `ask`/`deny` (`settings --apply`).
- **Hooks:**
  - de ~540 para ~250 ms por chamada no Windows;
  - novo doctor no SessionStart;
  - o log não grava mais eventos sem assinatura quando falta a chave privada.
- **Log:** checkpoints, segmentos arquivados, `rotate-key` e `anchor`.
- **Avaliações:** casos de `claude plugin eval` em `plugins/aisef/evals/`.
- **Documentação:** ícone, README em inglês e em português, passo a passo com capturas e template de `AGENTS.md`.
- **Decisões aplicadas:**
  - lista T1 ampliada;
  - autorização de escopo com validade máxima de 7 dias (política, gateway, `decide` e regra `AUTH-SCOPE-TOO-LONG`).
- **Agentes:**
  - o `aisef-init` gera os Agent Contracts dos 8 agentes como `draft`;
  - ativá-los é decisão do usuário (`aisef_project.py agents --activate`);
  - o gateway aplica o teto de cada subagente (o validador só usa Git de leitura).
- **Painel:**
  - aba Engenharia, que lê o blueprint (arquitetura, backend, frontend, banco com ER, segurança, DevOps e testes);
  - Mermaid em cópia local, para funcionar offline.
- **Novos testes no `check_project`:** `PAR-FILE-CONFLICT`, `PAR-PATH-OVERLAP` e `REPORT-CONSULTATIONS`.
- **Padrões do gateway:** os de banco e segredos foram reescritos do zero em `hooks/sensitive_patterns.json`, e o `db_patterns.json` foi removido. O AISEF não depende da `new-project-setup`.

## 0.1.0 - 2026-11-05
- Primeira versão como plugin do Claude Code, distribuída por marketplace.
- **Artefatos da conversa de origem**, com os testes passando:
  - política de permissões e padrões de orquestração;
  - 9 JSON Schemas;
  - `check_project` (mais de 60 regras) e `check_policy_consistency`;
  - cadeia de auditoria com hash e assinatura Ed25519;
  - painel HTML.
- **Novo:**
  - Execution Gateway (hook PreToolUse), que traduz a política em allow/ask/deny;
  - hook de auditoria (PostToolUse);
  - `aisef_project.py` com os comandos init, append, decide e verify;
  - 7 skills e 8 agentes especialistas;
  - `run_tests.py` e CI.
- **Correções nos testes do painel:**
  - a linha do tempo tem 11 eventos, porque o demo ganhou uma autorização de escopo;
  - detecção do Chrome no Windows;
  - leitura da saída do Chrome em UTF-8.
