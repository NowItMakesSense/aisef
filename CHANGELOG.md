# Changelog

## 0.9.0 - 2026-11-18
- **Modo Ask (ADR 0018):**
  - `/aisef:ask <pergunta>` responde num subagente `aisef:ask` (Haiku, effort baixo, só `Read`/`Grep`/`Glob`): barato e sem como editar;
  - `/aisef:modo ask|exec` (só o usuário digita) troca o modo da sessão; trocar abre o prompt nativo.
  - No modo Ask, o gateway nega Edit/Write, comandos que não sejam de leitura (com uma lista de leitura para Bash e PowerShell e redirecionamento negado) e MCP fora do `mcp_allow`. O hook `UserPromptSubmit` (`prompt_mode.py`) lembra o modelo a cada pergunta; no modo normal, fica em silêncio.
  - Novo guia `docs/guide/ask-mode.md`.

## 0.8.2 - 2026-11-18
- **`aisef-tooling`:**
  - **gatilhos explícitos de busca** (fim da discovery, feature com tecnologia nova, fatia travada por tecnologia desconhecida, pedido do usuário);
  - **revisão periódica** (seção 8): o `/skill-doctor` rodado pelo usuário, `claude plugin details`, `claude plugin eval --ablation with-without` com teto de custo e uma tabela manter/remover/trocar. Nada sai sem a escolha do usuário.
- **`next`:** `guide.tooling_review_due` avisa quando a revisão está vencida (padrão: a cada feature aceita; `"tooling": {"review_every": N}`, 0 desliga).
- **Gateway:** desinstalar ou desativar plugin, remover skill, remover marketplace e remover servidor MCP passam a pedir aprovação, como a instalação.

## 0.8.1 - 2026-11-18
- **Aprendizado contínuo revisado (`core/aisef_learn.py`, ADR 0017):**
  - lições a partir de **erros rotulados** (reprovações, `precheck`, bloqueios do gateway, `scope_discovery`, correções, problemas de relatórios), agrupados sem modelo (`propose`);
  - só viram lição com a **aprovação do usuário** (`accept`; o gateway abre o prompt nativo, e um subagente não aprova);
  - a **confiança é calculada em código** (`update`: sobe com sucesso, cai com reprovação, decai sem uso, aposenta abaixo de 0,2);
  - entra só no pacote da tarefa relevante, com confiança ≥ 0,5, como referência;
  - fica em `.aisef/knowledge/`, versionada (o time herda);
  - schema da memória com `lesson` e `status: retired`; nova regra `KNW-LESSON-EVIDENCE`.
- **Estado depois de `/compact` e `/resume`:** o doctor (`SessionStart` agora com `compact`) reinjeta fase, tarefas em andamento e decisões pendentes. O `next` traz `guide.compact_hint` nos marcos de fase sem agente em voo.
- **Painel:** a aba Agora mostra as lições (confiança, uso, aposentadas) e os agentes despachados por modelo.
- **Perfis de hook do ECC: descartados**, porque o gateway precisa rodar sempre (ADR 0017).

## 0.8.0 - 2026-11-18
- **Painel ao vivo (`build_panel.py --serve`):** servidor da stdlib em `127.0.0.1` que regenera os dados quando `.aisef/` muda. A página se atualiza sozinha a cada 3 s. No Windows o navegador não lê arquivo local por `file://`, daí o servidor. O modo estático continua.
- **Aba "Agora" (nova, a primeira):**
  - onde o projeto está e o próximo passo (do `next`), com as ações do orquestrador e o critério de parada;
  - **subagentes em execução**, com a fatia que receberam, há quanto tempo e a última ação;
  - **fluxo de cada feature** (Spec → Plano → Execução → Validação → Revisão e aceite → Encerrada) com a etapa atual destacada;
  - **ondas no tempo real** em Gantt, que mostram o que rodou em paralelo.
- **Hooks `SubagentStart`/`SubagentStop`** (`agent_events.py`, em segundo plano): gravam início e fim de cada subagente em `.aisef/runtime/agents.jsonl`, efêmero e fora do Git. A auditoria grava ali também a última ação de cada subagente. A trilha assinada continua no log de auditoria.
- **Estado efetivo no painel:** as tarefas aparecem com o estado real (contrato + último evento do log, a mesma regra do `next` e do check), não com o que o contrato ainda não registrou.
- **Aprovações:** o "Approval Center visual" do antigo `pending.md` fica coberto pelas abas Agora e Aprovações (só leitura); a decisão continua no prompt nativo.

## 0.7.0 - 2026-11-18
- **Despacho em uma chamada (`aisef_project.py dispatch`):** calcula a onda (mesma regra do `next`), monta pacote de contexto, modelo/effort e o prompt de cada agente, e registra os `delegation`. O orquestrador dispara todos na mesma mensagem. Antes eram 3 chamadas por tarefa (`pack`, `route`, `append`), cada uma pagando os hooks.
- **`precheck` determinístico:** relatório do executor, critérios obrigatórios `met` com evidência, TDD coerente, arquivos no escopo e, em UI, nada fora dos tokens. Sem modelo e sem executar comandos do projeto.
- **`validate-wave`:** quem falha no `precheck` volta ao executor (tentativa + 1, sem gastar validador). O resto da onda vai para **um** validador, com veredito por tarefa (ADR 0016).
- **Auditoria assíncrona** de Edit/Write/MCP (`async` no `hooks.json`). Bash e PowerShell continuam síncronos, por causa da aprovação reforçada de uso único.
- A skill `aisef` passa a usar `dispatch` e `validate-wave` no modo contínuo.
- **Worktrees por fatia ficaram para depois:** exigem antes uma mudança de política (merges locais por escopo) que é decisão do usuário (roadmap).

## 0.6.1 - 2026-11-18
- **Autoridade de design por projeto (nova skill `aisef-design`, ADR 0015):**
  - `.aisef/design/tokens.json` (novo schema `design-tokens`) e `DESIGN.md` definem tipografia, paleta, espaçamento, movimento, componentes e regras, aprovados como decisão arquitetural.
  - UI/UX Pro Max, Taste e Impeccable entram como fontes, cada uma no seu papel, sempre dentro dos tokens.
- **`core/design_check.py`:**
  - `validate`;
  - `scan`: cores e fontes do código de UI fora dos tokens, com arquivo e linha, sem modelo;
  - `shots`: capturas em 375, 768 e 1440 px em Chrome/Edge headless.
- **Integração:**
  - o pacote de contexto das fatias de UI traz os tokens e o comando de conferência;
  - o `aisef_new.py feature` acrescenta a cada fatia de UI o critério "nada fora dos tokens";
  - regras novas no check: `DESIGN-SCHEMA`, `DESIGN-UNAPPROVED` e `DESIGN-MISSING` (aviso).
- **Agente `frontend`:** implementa e revisa dentro dos tokens, com a ferramenta `Skill` para usar as skills de design. A evidência visual passa a ser obrigatória. O padrão do papel sobe para L3 (sonnet/medium).
- **Gateway:** nega abrir o `claude` com `--dangerously-skip-permissions` ou `--permission-mode bypassPermissions`. O `impeccable live` pede aprovação.
- **`aisef-tooling`:** recomenda as três skills de design, com instalação e riscos. A `aisef-discovery` encaminha para a `aisef-design` em projetos com UI.

## 0.6.0 - 2026-11-18
- **SDD + TDD como padrão, com o método do Matt Pocock:**
  - **Fases da `aisef-feature`:** Grill (perguntas uma de cada vez até fechar cada ramo), Spec (solução, histórias, decisões e **seams de teste** confirmados com o usuário) e **Fatias verticais** (tracer bullets com blocking edges), depois a aprovação do plano e o Blueprint.
  - **Brief:** ganha `spec` e fatias (`kind: "slice"`, `touches`, `seams`). Uma fatia sai com `tests.tdd_required`. O `example feature` passa a mostrar fatias verticais. Brief sem `spec` continua válido (compatível com 0.5).
- **Novo agente `implementer`:** faz a fatia inteira com TDD. Tem a ferramenta `Skill` e pré-carrega `mattpocock-skills:tdd` quando o plugin existe. Os especialistas passam a revisar as fatias que tocam a área deles. O validador confere a evidência de TDD.
- **Evidência de TDD checada:**
  - o Execution Report ganha `tdd_evidence.cycles`, com as execuções vermelha e verde (comando, exit code, horário);
  - regras novas: `TDD-RED-NOT-FAILING`, `TDD-GREEN-FAILING`, `TDD-RED-BEFORE-GREEN`, `TDD-EVIDENCE-MISSING`, `SPEC-REQUIRED`, `SPEC-SEAM-UNKNOWN` e `SLICE-NO-AUTOMATED-TEST` (144 regras ao todo).
- **Guia de fases:**
  - o `next` devolve `guide`: a fase do projeto (discovery, specify, approve_plan, execute, review, decide, done), o próximo passo com a skill certa e o mapa dos comandos do Matt (`/to-spec` → fase Spec etc.);
  - a skill `aisef` passa a dizer "Estamos em X. Próximo: Y" antes de começar a codar.
- **Code review antes do aceite:** com todas as fatias concluídas, a feature passa pela skill `code-review` (padrões + aderência à spec) antes do pedido `feature_acceptance`.
- **Plugin do Matt:** o `aisef-init` oferece instalar `mattpocock-skills` no escopo do projeto. Não é uma dependência declarada (ADR 0014).
- **Atualização de projetos existentes:** o doctor avisa quando falta o `implementer`. `aisef_project.py agents` cria o draft, e `agents --activate --roles implementer` ativa o agente e faz o validador passar a validá-lo (nova versão do contrato, registrada no log).
- **Evals:** `feature-choice` exige fatias verticais com teste primeiro; nova `spec-guidance` (pedir uma spec depois de uma conversa leva às fases certas).

## 0.5.3 - 2026-11-18
- **Documentação reorganizada** ([docs/README.md](docs/README.md)):
  - `guide/`: conceitos, fluxo de trabalho e passo a passo;
  - `reference/`: política, comandos, hooks e as regras do check;
  - `adr/`: 13 decisões de arquitetura;
  - `roadmap.md`;
  - `history/vision.md`: a visão original, convertida para markdown e sem as marcas da conversa em que foi escrita.
- **README** (EN e PT) reescrito: o que é, por quê, fluxo em diagrama, instalação, início em 5 minutos e limites honestos. A política detalhada foi para `docs/reference/policy.md`.
- **`decisions.md` virou ADRs** e **`pending.md` virou `roadmap.md`**. Dos 5 itens pendentes, 3 já estavam feitos, a âncora externa foi descartada (ADR 0005) e o Approval Center visual vira a aba "Decisões" do painel vivo.
- **`tools/gen_docs.py`** gera `docs/reference/check-rules.md` a partir do código (137 regras; a documentação dizia "mais de 60"). O `run_tests.py` acusa quando a referência fica desatualizada.

## 0.5.2 - 2026-11-18
- **Correção crítica: o gateway e a auditoria agora cobrem a ferramenta PowerShell.** No Windows, o Claude Code também executa comandos pela ferramenta `PowerShell`, que não estava nos matchers do `hooks.json`. Por ela, `git push`, `Remove-Item -Recurse` ou `Get-Content .env` passavam sem política e sem registro. Agora o PowerShell segue a mesma política do Bash: Git por operação, arquivos sensíveis, banco, deploy, T1 e o teto do Agent Contract nos subagentes. Os comandos também vão para o log.
- **Padrões do shell ampliados:**
  - remoção recursiva com os aliases do PowerShell (`rm -r`, `ri -Rec`, `del /s`, `rd /s`);
  - despejo de ambiente por `[Environment]::GetEnvironmentVariables()`;
  - **escrita por shell em arquivos de decisão do AISEF** (`> .aisef/config.json`, `Set-Content .aisef/approvals/...`, `cp`/`sed -i` em autorizações e Agent Contracts) passa a pedir aprovação, e subagentes têm essa escrita negada. Antes, só a escrita pelas ferramentas Edit e Write era protegida.
- **Um processo a menos por Grep e Glob:** o lembrete do grafo (`graph_nudge`) roda dentro do processo do gateway, em vez de abrir um segundo Python a cada busca.
- **`tools/bench_hooks.py`:** mede a latência dos hooks como o Claude Code os chama. No Windows deste desenvolvimento, a mediana fica entre ~170 e ~270 ms por hook, quase toda gasta abrindo o processo.
- **CI em Linux e Windows**, com a checagem de que `plugin.json` e `marketplace.json` estão com a mesma versão e a latência dos hooks (informativa).

## 0.5.1 - 2026-11-06
- **`check_project` aceita a raiz do repositório:** `--project .` (como os demais comandos) passa a checar `.aisef/` quando existe `.aisef/config.json`. Antes, a raiz não tinha documento nenhum e o validador respondia "0 erro(s)" sem checar nada; no uso real isso escondeu 22 erros.
- **Nova regra `PROJECT-EMPTY`:** pasta sem documento AISEF e sem log de auditoria é erro, e não passa mais como projeto limpo.
- **`check_project` usa o estado efetivo da tarefa** (contrato + último evento do log, a mesma regra do `next`). Contrato que ficou em `ready` depois do `task_completed` não é mais checado como tarefa aberta, e as regras de estado passam a valer para o que de fato aconteceu.
- **Caminho rápido no `check_project`:** tarefa da `FEAT-MAINT` sem validador independente conclui direto, sem `task_started`, `task_executed` nem Execution Report (como a skill manda); o `task_completed` continua obrigatório.
- **`PERM-SCOPE-REQUIRED` em tarefa concluída vira aviso** (histórico), como já era o `AGENT-PATH-CEILING`.
- **Intervenção resolvida fora do executor:** se a tarefa foi validada pelo validador independente depois, relatório sem status `executed` (`STATE-REPORT-STATUS`) e ausência de `task_executed` (`STATE-NO-EXEC-EVENT`) viram aviso; sem a validação continuam erro.
- **Execution Report aceita `sha256_before`** em `files` (hash do arquivo antes da alteração), que os agentes já gravavam.
- **Aprovação reforçada consumida:** o hook de auditoria (PostToolUse) marca a reforçada como `used`, com `consumed.operation_event_ref` apontando o `tool_used` da operação exata. Antes nada a consumia, ela vencia como `approved` e o `aisef-check` acusava `AUTH-REINFORCED-EXPIRED`.
- **`next` tolera relatório fora do schema:** `risks` com texto em vez de objeto, ou `intervention` que não é objeto, não derrubam mais o comando (antes: `AttributeError`). O resultado ganha `warnings` com o relatório a corrigir e manda rodar o `aisef-check`.

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
- **Artefatos da especificação original**, com os testes passando:
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
