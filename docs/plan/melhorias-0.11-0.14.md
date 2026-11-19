# Plano: subir a nota do AISEF (0.11 → 0.15)

> **Status:** proposto, 2026-11-19.
> **Origem:** análise de 2026-11-19 (nota geral 6,3; ferramenta pessoal 7,0; produto 4,5).
>
> **Regra de ritmo: congelamento de funcionalidades.** Nada fora deste plano entra até a 0.12 rodar num projeto real com a versão atual e bater as metas da seção 8. Correção de defeito não está congelada.

## 1. Objetivo

Elevar todas as notas da análise, priorizando quem usa sozinho (solo primeiro, times depois):
- **Provar valor com dado:** `metrics` e benchmark de resultado.
- **Cortar o custo de atenção:** MCP e Git por risco, ciclo de vida registrado por código.
- **Amadurecer o loop e o grafo:** orçamento, worktrees, workflow declarativo, Graphify como padrão.
- **Abrir a porta para times:** verificação no CI, pacote de evidência, um stream de log por pessoa.

## 2. Decisões tomadas na entrevista

| Tema | Decisão |
|---|---|
| Público | Solo primeiro. Times na 0.14 e 0.15 |
| Git | Commit livre em `feat/*`; push coberto pelo escopo da feature. `main`, merge, release e force ficam como estão. Novo ADR substitui o ADR 0004:16 |
| Log | O log assinado guarda ciclo de vida, decisões, tudo que o gateway negou ou perguntou, e Bash/PowerShell. Edit/Write/MCP liberados vão para a telemetria |
| MCP | Escopo por ferramenta, por projeto, com até 7 dias e renovável. Ferramentas que executam código arbitrário continuam perguntando, a não ser que o usuário marque |
| Isolamento | `/sandbox` nativo recomendado pelo init e pelo doctor, mais um corpus de testes do gateway. No Windows, só o gateway |
| Benchmark | Pequeno e manual: 6 tarefas × 2 braços (Claude Code puro e AISEF) × 3 repetições, em Linux ou WSL |
| Multiusuário | Um stream por pessoa. Spike e ADR na 0.14, implementação na 0.15 |
| Perfil padrão | `solo` para projetos novos |
| Grafo | **Graphify passa a ser padrão** nos projetos AISEF e também é usado no próprio repositório. O codebase-memory-mcp segue opcional e é medido antes de decidir |
| Entrega | Este arquivo, versionado, com IDs de tarefa e congelamento de funcionalidades |

## 3. Diagnóstico por área: o que falta para cada nota subir

| Área | Hoje | Meta | O que está faltando (evidência no código) | Tarefas |
|---|---|---|---|---|
| Tese e visão | 8,0 | 8,5 | A tese é "menos instabilidade", mas o README vende números de engenharia | D-01 |
| Engenharia do código | 8,5 | 9,0 | `check_project.check()` é uma função de 941 linhas sem registro de regras, e regra nenhuma tem sugestão de correção | F-07, L-03 |
| Documentação | 8,5 | 9,0 | Não há números de resultado. O guia do perfil `solo` não existe | D-01, L-04 |
| Gateway | 7,0 | 8,5 | Pergunta a cada chamada MCP fora do `mcp_allow`. Git sem branch: todo commit e push pergunta. `git add`, `switch` e `worktree` não têm classificação e são negados aos subagentes. Há falsos positivos (ex.: `git rm -r --cached` conta como remoção recursiva). Não há sandbox | F-01, F-02, F-03, F-08 |
| Auditoria | 7,0 | 8,5 | Toda chamada de ferramenta vira evento assinado (`audit_hook.py:60`, `gateway.py:115`). A verificação só roda localmente | F-05, T-01 |
| Processo SDD e TDD | 7,0 | 8,0 | Contratos desatualizam sem caminho barato de correção (`TASK-REQ-VERSION` só acusa). Não há `plugin_version` nem `migrate` | F-06, F-07, M-03 |
| Loop | 6,5 | 8,5 | Não há orçamento (`timeout_minutes` nunca é lido). Não há worktrees. O agente registra o próprio `task_started`/`task_executed` (`aisef_dispatch.py:54-68`). A ligação subagente → tarefa é heurística (`panel_live.py:184`) | F-04, L-01, L-02 |
| Observabilidade | 7,5 | 8,5 | Faltam tokens e custo por tarefa, e o custo de atenção não aparece no painel | M-02, F-09 |
| Graph engineering | 5,0 | 7,5 | O grafo do sistema está espalhado em 4 lugares. O Graphify é opcional e não medido | G-01…G-05, L-03 |
| Custo de atenção | 4,5 | 8,0 | Itens do gateway, mais aprovação Git por operação (ADR 0004), mais cerimônia igual para tudo | F-01…F-04, L-04 |
| Evolução sem quebrar | 4,0 | 8,0 | Não há `plugin_version`, `migrate` nem `--fix` | F-06, F-07 |
| Prova de valor | 2,5 | 6,5 | Os evals só testam acionamento. Não há benchmark | M-01…M-05 |
| Times | 3,0 | 6,5 | Chave e head locais, cadeia linear, nada no CI, sem pacote de evidência | T-01…T-05 |

## 4. Requisitos

### Funcionais
- Como usuário solo, eu quero aprovar uma ferramenta MCP ou o push de uma feature uma vez, para não ser interrompido a cada chamada.
- Como usuário, eu quero ver interrupções humanas por tarefa, tokens e lead time, para saber se o AISEF compensa.
- Como orquestrador, eu quero que o ciclo de vida das tarefas seja registrado por código, para que o estado nunca dependa de o modelo lembrar de um comando.
- Como usuário, eu quero que o projeto acompanhe a evolução do plugin (`migrate`) e que o check diga como corrigir cada erro.
- Como usuário, eu quero que o loop pare por orçamento e rode fatias em worktrees, para deixá-lo trabalhando sem medo.
- Como time, eu quero que a PR seja barrada se o log foi adulterado, se falta TDD ou se falta rastreabilidade, e quero um pacote de evidência por release.

### Não funcionais
- **Desempenho:** o gateway continua com cerca de 0,2 s por chamada (`tools/bench_hooks.py`). Nada novo roda síncrono no `PreToolUse` sem medir.
- **Segurança:** falha fechada mantida. Cada afrouxamento (MCP, Git) tem ADR, teste de negação e exceção para o que é irreversível ou executa código arbitrário.
- **Compatibilidade:** Windows (Git Bash) e Linux. Projetos antigos continuam funcionando até rodarem `migrate`, e o comportamento antigo é o padrão para eles.
- **Privacidade:** o Graphify roda por padrão com `GRAPHIFY_BACKEND=none` (só a parte estrutural, nada enviado a um provedor de modelo). O passo semântico é opt-in.
- **Rastreabilidade:** toda mudança de política gera ADR, CHANGELOG e testes. `gen_docs` e `gen_agents` ficam em sincronia.

## 5. Plano de tarefas

Estimativas em dias de trabalho seu com o Claude, como faixa.
- **Responsável:** você, com o Claude implementando.
- **Fechamento de cada tarefa:** testes no `run_tests.py`, docs e CHANGELOG.

### 0.11: Medir e Graphify padrão

```
[x] M-01: aisef_project.py metrics
    Feito na branch feat/v0.11-metrics (core/aisef_metrics.py, test_metrics.py, 15 testes).
    Falta: commit e PR.

[x] M-02: Tokens e duração por tarefa
    Feito: o SubagentStop soma o usage do agent_transcript_path (a doc oficial confirma que o hook
      não traz usage) em .aisef/runtime/usage.jsonl, com tarefa, modelo e duração. O metrics ganha
      a seção Custo. Validado num transcript real.
    Mudança de escopo: execution_profile.usage no schema foi descartado (o agente não sabe os
      próprios tokens). O dado vai para o task_executed na F-04.
    Bônus da F-04 já entregue: ligação exata subagente → tarefa pelo "T-xxx:" do disparo
      (core/aisef_runtime.py).

[ ] M-03: Harness do benchmark de resultado
    Descrição: tools/bench_outcomes.py e bench/ com 6 tarefas em repositórios fixture
      (2 de feature, 2 de bug, 1 de refatoração, 1 de segurança), cada uma com testes escondidos
      fora do alcance do agente. Dois braços via claude -p: Claude Code puro e AISEF com escopo
      pré-concedido.
    Medidas: testes escondidos passando, tokens, tempo, prompts ou negações, regressões
      em testes existentes.
    Depende de: M-02 (tokens)
    Critério de aceite: uma execução gera docs/benchmarks/<data>.md com a tabela por braço;
      roda em Linux ou WSL com um comando só.
    Estimativa: 3–5 dias (confiança média)

[ ] M-04: Eval de resultado no plugin
    Descrição: o caso evals/outcome-slice (tag shell) roda os testes escondidos e o
      check_project no fixture depois do agente.
    Depende de: M-03 (reaproveita um fixture)
    Critério de aceite: passa com o plugin e falha num fixture sabotado.
    Estimativa: 1 dia

[ ] M-05: Linha de base num projeto real com a versão atual
    Descrição: depois de você limpar o deckloom (ou num projeto novo), rodar 1 feature
      completa e o metrics. Gravar docs/benchmarks/baseline-<projeto>.md.
    Depende de: M-01, M-02 e a limpeza do deckloom (sua)
    Critério de aceite: linha de base publicada. As metas da seção 8 ganham números reais.
    Estimativa: 1 dia de uso + 0,5 de registro

[x] G-01: Graphify padrão no aisef-init
    Descrição: no aisef-init, o Graphify vem marcado (opt-out). Um único OK seu instala no
      escopo do projeto (o ADR 0011 continua valendo: instalar passa pelo gateway).
      GRAPHIFY_BACKEND=none por padrão. Gera o grafo sobre docs/ e .aisef/.
      O codebase-memory-mcp continua opt-in.
    Depende de: nenhuma
    Critério de aceite: o eval init-trigger mostra o Graphify pré-marcado; recusar não quebra
      nada; o doctor avisa quando o grafo está velho (mais antigo que o último contract_changed).
    Estimativa: 1–2 dias

[x] G-02: O pack usa o Graphify por padrão
    Descrição: o aisef_context.py pack, com o Graphify presente, inclui o resultado das
      consultas (não só a sugestão) de decisões e specs ligadas à tarefa, limitado em tokens.
      Novo modo --no-graph.
    Depende de: G-01
    Critério de aceite: test_context cobre com grafo, sem grafo e com grafo velho; o pacote
      nunca passa do limite.
    Estimativa: 2–3 dias (confiança média: a API do Graphify não está toda documentada)

[ ] G-03: Reconstruir o grafo nos marcos
    Descrição: o next sugere atualizar o grafo depois de contract_changed, do blueprint
      aprovado e do aceite de feature. Sem hook de git (o README do Graphify altera .git/hooks).
    Depende de: G-01
    Critério de aceite: test_next cobre a sugestão.
    Estimativa: 0,5–1 dia

[x] G-04: Graphify no repositório do AISEF
    Descrição: instalar (uv tool install graphifyy, com a sua aprovação), rodar sobre docs/,
      ADRs e skills, e registrar o uso no README de desenvolvimento.
      graphify-out/ fica no .gitignore.
    Depende de: nenhuma (é ação sua mais a minha)
    Critério de aceite: /graphify query responde sobre os ADRs; a seção de desenvolvimento
      está documentada.
    Estimativa: 0,5 dia

[ ] G-05: Medir o efeito do grafo
    Descrição: o dispatch registra context_mode (graphify, codebase-memory, nenhum) no
      delegation.data; o metrics compara 1ª validação, tokens e lead time por modo.
    Depende de: M-01, M-02, G-02
    Critério de aceite: o metrics mostra a comparação. Depois de cerca de 20 tarefas,
      decisão registrada em ADR: manter, rebaixar ou remover o codebase-memory-mcp,
      e confirmar o Graphify como padrão.
    Estimativa: 1 dia + coleta
```

### 0.12: Cortar fricção e ganhar confiança

```
[ ] F-01: MCP por escopo de ferramenta
    Descrição: novo recurso mcp_tool no authorization.schema (resource_filters.tools com
      globs) e no approval-request (scope_proposal). O scope_covers (gateway.py:291) passa a
      casar a ferramenta. Lista executes_code em sensitive_patterns.json (execute_*,
      javascript_tool, eval*, run_*): perguntam sempre, a não ser que haja
      allow_code_execution: true explícito.
      A aisef-approve oferece "confiar nesta ferramenta" no primeiro prompt.
    Depende de: nenhuma
    Critério de aceite: test_gateway cobre ferramenta com escopo → allow; sem escopo → ask;
      executes_code com escopo comum → ask; com allow_code_execution → allow; escopo vencido → ask.
      O check aceita o recurso (AUTH-NOT-SCOPABLE). Novo ADR 0020.
    Estimativa: 2–3 dias

[ ] F-02: Corpus de testes do gateway (falsos positivos e negativos)
    Descrição: hooks/corpus/*.jsonl com comando e decisão esperada, cobrindo heredoc,
      git rm --cached, loops com gh, pipes legítimos e tentativas de contorno conhecidas.
      test_gateway lê o corpus. Ajustar RM_RECURSIVE_RE (não marcar git rm --cached),
      OBFUSCATED_RE e o GIT_RE (pular -c k=v).
    Depende de: nenhuma
    Critério de aceite: corpus com pelo menos 80 casos, 0 regressões e cada falso positivo
      conhecido coberto.
    Estimativa: 2–3 dias

[ ] F-03: Git por risco
    Descrição:
      - core/aisef_git.py com current_branch(), extraído de aisef_next.git_state
        (aisef_next.py:86); falha fechada.
      - Novas ops commit_feature (allow em dev e staging), push_feature (approve_scope)
        e local_staging (add, switch, switch -c; allow).
      - Recurso git_feature_branch com resource_filters.branches. O scope_covers confere a
        branch contra a feature.
      - Nova regra AUTH-GIT-BRANCH.
      - A aisef-feature cria o pedido de escopo junto com o plan_approval, e a aisef-approve
        mostra os dois juntos.
      - O implementer ganha commit_feature e local_staging (gen_agents).
      - Novo ADR 0021, substituindo o ADR 0004:16.
    Depende de: nenhuma (compartilha o scope_covers com F-01: fazer depois de F-01)
    Critério de aceite (todos em test_gateway):
      - commit em feat/x → allow; commit em main → ask;
      - push de feat/x com escopo → allow, sem escopo → ask;
      - feat/x:main → ask; --force → deny;
      - branch indetectável → ask.
      O SKILL.md (regra 8 e "Branch por feature") é atualizado.
    Estimativa: 3–4 dias

[ ] F-04: Ciclo de vida registrado pelos hooks
    Descrição:
      - agent_events.py extrai T-xxx: do description do spawn aisef:* e grava o task_id.
      - _match_parents sai de panel_live.py:184 e vai para o novo core/aisef_runtime.py.
      - SubagentStart com casamento seguro → task_started (ator agent = assigned_agent,
        data.recorded_by=hook).
      - SubagentStop com RPT executado depois do start → task_executed (com o usage do M-02).
        Sem relatório, o next emite await_decision com a fonte no_report.
      - Validador: grava reports/VAL-<onda>.json e o Stop registra task_validated/task_rejected.
      - Idempotente: se o último evento já é esse, não grava de novo.
      - Remove do executor_prompt os passos de append.
    Depende de: M-02 (payload confirmado)
    Critério de aceite: novo hooks/test_agent_events.py cobre casamento seguro, inferido
      (não grava), sem relatório e duplicado. test_dispatch e test_next atualizados.
      LOG-TASK-ACTOR nunca dispara num fluxo normal.
    Estimativa: 3–4 dias (confiança média)

[ ] F-05: Log em camadas
    Descrição: core/telemetry.py com .aisef/telemetry/telemetry.jsonl (cadeia de hash
      própria, sem assinatura, rotação, gitignored). audit_hook manda Edit/Write/MCP
      liberados para a telemetria; o gateway manda allow para a telemetria e mantém deny
      e ask assinados. Config audit.telemetry: split|signed (split nos novos; os antigos
      ficam em signed até o migrate). O metrics e o painel leem os dois.
    Depende de: F-06 (o migrate liga o split nos projetos antigos)
    Critério de aceite: test_audit_lifecycle mostra o que vai para cada lado;
      consume_reinforced continua funcionando; bench_hooks sem regressão;
      tool_used_share abaixo de 0,5 numa feature típica.
    Estimativa: 2–3 dias

[ ] F-06: plugin_version e migrate
    Descrição: o init grava plugin_version no config. O doctor compara com o plugin.json e
      sugere o migrate. Novo core/aisef_migrate.py com migrações ordenadas e idempotentes,
      --dry-run como padrão e --apply passando pelo prompt nativo. Cada mudança gera evento.
      Primeiras migrações: plugin_version, audit.telemetry, profile=team para projetos
      antigos (preserva o comportamento atual).
    Depende de: nenhuma
    Critério de aceite: novo test_migrate cobre um projeto 0.10 → 0.12 sem perder nada,
      a segunda execução sem mudanças e o dry-run sem escrever.
    Estimativa: 2–3 dias

[ ] F-07: check --fix e rebase-req
    Descrição: Report.add ganha fix {cmd|hint} (check_project.py:83); o JSON passa a sair
      como {severity, rule, where, message, fix?}. Fixes para TASK-REQ-VERSION,
      PLAN-*-VERSION, RTM-TASK-NOT-LINKED, VAL-NO-VALIDATOR, AGENT-PATH-CEILING,
      DESIGN-MISSING e STATE-*. Novo aisef_new.py rebase-req --task --req (mostra o diff do
      requisito e grava contract_changed; tarefa concluída → sugere reabertura). O next
      emite requirement_changed antes de virar erro. Ao mexer nas regras, extrair um
      registro de regras (passo para L-03).
    Depende de: F-06
    Critério de aceite: test_check_project confere que cada regra coberta traz fix;
      um projeto com divergência de versão volta a 0 erros só com os comandos sugeridos.
    Estimativa: 3–4 dias

[ ] F-08: Sandbox nativo recomendado
    Descrição: o aisef-init oferece ativar o /sandbox do Claude Code onde existir (Linux,
      macOS). O doctor avisa no SessionStart quando está desligado. A doc de política
      explica as camadas (sandbox isola, gateway decide, log prova).
    Depende de: nenhuma
    Critério de aceite: o doctor detecta e avisa (teste com config simulada); no Windows
      só informa, sem bloquear.
    Estimativa: 1 dia (confiança média: confirmar como o Claude Code expõe o estado do sandbox)

[ ] F-09: Custo de atenção como métrica principal
    Descrição: o metrics calcula interrupções humanas por tarefa concluída (pedidos mais
      asks do gateway). O painel mostra essas interrupções, os tokens por tarefa e a
      1ª validação na tela Agora.
    Depende de: M-02, F-05
    Critério de aceite: test_panel cobre o card; o número bate com o metrics.
    Estimativa: 1–2 dias

[ ] F-10: Uso real e fechamento da 0.12
    Descrição: 1 feature real com a 0.12, o metrics comparado com o M-05 e o registro
      em docs/benchmarks/.
    Depende de: F-01…F-09, M-05
    Critério de aceite: metas da seção 8 batidas ou desvio explicado. É o fim do
      congelamento de funcionalidades.
    Estimativa: 1–2 dias
```

### 0.13: Loop e grafo do sistema

```
[ ] L-01: Orçamento no loop
    Descrição: lê limits.timeout_minutes e o novo max_tokens; o feature contract ganha
      budget {max_minutes, max_tokens, max_attempts_total}, com padrões em
      orchestration-defaults. O next (aisef_next.py:268-280 e :413) ganha o stop_reason
      budget_exhausted logo depois de critical_risk.
    Depende de: M-02
    Critério de aceite: test_next cobre os limites por tempo, por tokens e por tentativas;
      elevar o limite exige aprovação.
    Estimativa: 1–2 dias

[ ] L-02a: Raiz do projeto via git-common-dir (pré-requisito)
    Descrição: aisef_git.project_root(cwd) usa git rev-parse --git-common-dir e é usado
      pelo gateway, pelo audit_hook, pelo agent_events e pelo aisef_project. Assim, um
      agente dentro de um worktree grava no .aisef/ principal, nunca na cópia.
    Depende de: F-03 (aisef_git)
    Critério de aceite: teste com worktree real mostra o evento indo para o log principal.
    Estimativa: 1–2 dias

[ ] L-02: Worktrees por fatia
    Descrição: config parallel.mode: paths|worktree. O dispatch devolve o comando de
      git worktree add .worktrees/T-xxx -b slice/<feat>/T-xxx. Novas ops worktree_local
      (allow em dev) e merge_feature (approve_scope pelo git_feature_branch). O
      strip_project_cd aceita .worktrees/. Em modo worktree, o compute_waves deixa de
      separar por conflito de paths. Conflito no merge vira task_rejected com
      merge_conflict. A ação complete faz o merge e remove o worktree.
    Depende de: L-02a, F-03
    Critério de aceite: test_waves, test_dispatch e test_gateway cobrem o ciclo; duas
      fatias com arquivo em comum rodam em paralelo e o conflito vira nova tentativa.
      O item adiado sai do roadmap.
    Estimativa: 4–6 dias (confiança baixa a média)

[ ] L-03: Workflow declarativo (grafo do sistema)
    Descrição: core/workflow.v0.1.json com schema: nós (fases e portões), transições
      (eventos), portões (tipos de aprovação) e agentes por nó. O EVENT_STATE
      (aisef_next.py:42), o guide, o diagrama de fluxo do painel e o check passam a ler o
      workflow. Passo 1 sem mudança de comportamento: todos os testes atuais passam intactos.
    Depende de: F-07 (registro de regras)
    Critério de aceite: diff de comportamento zero; novo test_workflow valida o schema
      e a coerência (todo evento tem estado, todo portão tem request_type).
    Estimativa: 3–5 dias

[ ] L-04: Perfis de cerimônia (solo como padrão)
    Descrição: config.profile solo|team|regulated como sobreposição do workflow.
      - solo (padrão nos novos): blueprint opcional em risco baixo, code-review só no
        aceite, TDD exigido em fatias com lógica.
      - team: o comportamento atual.
      - regulated: blueprint, TDD e revisão de segurança obrigatórios em risco alto,
        check --strict.
      O perfil muda os portões do next e a severidade do check. O gateway não muda.
      O init pergunta o perfil com solo pré-marcado. Novo ADR 0022.
    Depende de: L-03, F-06 (projetos antigos migram para team)
    Critério de aceite: test_workflow e test_next cobrem os três perfis; o eval
      feature-choice continua passando no solo.
    Estimativa: 2–3 dias

[ ] L-05: Uso real e fechamento da 0.13
    Descrição: rodar uma feature em /loop com orçamento e worktrees e comparar o metrics.
    Critério de aceite: o loop para por orçamento quando deve; lead time igual ou menor
      que na 0.12.
    Estimativa: 1–2 dias
```

### 0.14: Times (evidência)

```
[ ] T-01: GitHub Action aisef-verify
    Descrição: composite action em .github/actions/aisef-verify/. Roda
      aisef_project.py verify (só chaves públicas) contra o head.json versionado e
      assinado, e check_project --strict --json. Novo modo --pr: tarefas tocadas
      validadas, tdd_evidence em ordem e RTM coberta. Gera job summary em markdown.
      Fica ativa no próprio repositório sobre o demo.
    Depende de: F-05, F-07
    Critério de aceite: uma PR de teste falha com log truncado, com TDD fora de ordem e
      com requisito sem tarefa, e passa limpa.
    Estimativa: 3–4 dias

[ ] T-02: Pacote de evidência por feature e release
    Descrição: aisef_project.py evidence --feature --out reúne contrato, RTM, relatórios,
      aprovações, o trecho do log com o resultado do verify e o check, mais a tabela de
      controles: SOC 2 CC8.1 e ISO 27001 A.8.32 (aprovação, teste, separação de funções).
    Depende de: T-01
    Critério de aceite: test_evidence; o pacote do demo é legível e se verifica sozinho.
    Estimativa: 2–3 dias

[ ] T-03: Exportação OTel
    Descrição: aisef_project.py export-otel. Cada delegation vira um span por tarefa e a
      telemetria vira spans filhos, com atributos gen_ai.*. Antes, confirmar o estado
      das convenções semânticas GenAI do OpenTelemetry.
    Depende de: F-05
    Critério de aceite: o JSON exportado valida contra o formato OTLP; teste com o demo.
    Estimativa: 2 dias (confiança média)

[ ] T-04: Spike e ADR do stream por pessoa
    Descrição: protótipo de .aisef/audit/streams/<user>/ com chave por pessoa, verify de
      vários streams e ordenação por tempo, e aprovações assinadas pela chave de quem
      decidiu. Merge de branches sem conflito no log.
    Critério de aceite: ADR 0023 aceito; o protótipo passa num repositório com 2
      usuários simulados e 1 merge.
    Estimativa: 3–4 dias (confiança baixa)
```

### 0.15: Times (vários usuários)

```
[ ] T-05: Implementar os streams por pessoa
    Descrição: o que o ADR 0023 decidir; o migrate converte o log único no stream do dono.
    Depende de: T-04
    Estimativa: 5–8 dias (confiança baixa; depende do spike)
```

### Transversal

```
[ ] D-01: README com números de resultado
    Descrição: "What's new" e a tabela de topo passam a mostrar interrupções por tarefa,
      1ª validação e o resultado do benchmark (M-03), em vez de só regras e checks.
    Depende de: M-03, F-10
    Estimativa: 0,5 dia
```

**Critério de pronto de toda versão:**
- `run_tests.py` verde em Linux e Windows;
- `claude plugin validate`;
- `bench_hooks` sem regressão;
- `gen_docs` e `gen_agents` em sincronia;
- ADR, CHANGELOG e bump de versão no `plugin.json` e no `marketplace.json`.

## 6. Estimativa total

| Versão | Faixa (dias) | Confiança |
|---|---|---|
| 0.11 | 11–17 | média (payload do hook e API do Graphify) |
| 0.12 | 20–29 | média |
| 0.13 | 12–20 | baixa a média (worktrees) |
| 0.14 | 10–13 | média |
| 0.15 | 5–8 | baixa |
| **Total** | **58–87 dias de trabalho** | média |

**Premissas:**
- Um desenvolvedor com o Claude.
- O uso real de cada versão conta na faixa.
- Não inclui o tempo de você limpar o deckloom nem o custo em tokens do benchmark.

## 7. Riscos e dependências

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| O payload de `SubagentStart`/`SubagentStop` não traz `usage` nem `transcript_path` | Média | Alto (M-02, F-04, L-01) | M-02 vem primeiro e confirma. Plano B: só duração, e tokens pelo transcript da sessão principal |
| Afrouxar Git e MCP reduz a segurança | Média | Alto | ADR por mudança, exceção para o que executa código e para `main`/force, testes de negação no corpus (F-02) |
| Worktree grava no `.aisef/` da cópia | Alta sem L-02a | Alto | L-02a é pré-requisito obrigatório, com teste de worktree real |
| A API do Graphify muda ou não está documentada | Média | Médio | Seguir `grafo-de-codigo.md`, fixar versão e degradar para "sem grafo" sem quebrar |
| O passo semântico do Graphify envia docs a um provedor | Baixa (padrão `none`) | Alto | `GRAPHIFY_BACKEND=none` por padrão; opt-in explícito |
| O benchmark não mostra ganho | Média | Alto (tese) | É informação: ajustar o perfil `solo` ou a tese. Publicar mesmo assim |
| Não há sandbox no Windows | Certa | Médio | Avisar no doctor; o gateway continua sendo a camada |
| O workflow declarativo muda comportamento sem querer | Média | Médio | Passo 1 com diff zero; todos os testes atuais intactos |
| Mudanças futuras do Claude Code quebram hooks | Média | Médio | Doctor com versão mínima; CI em Linux e Windows |

**Dependências externas:**
- você limpar o deckloom (M-05);
- a documentação oficial dos hooks do Claude Code (M-02, F-08);
- Linux ou WSL para o benchmark;
- a sua aprovação para instalar o Graphify neste repositório (G-04).

**Ordem crítica:**
- M-02 → F-04 → F-09 → F-10;
- F-01 → F-03 → L-02a → L-02;
- F-06 → F-07 → L-03 → L-04;
- F-05 → T-01 → T-02.

## 8. Critérios de aceite gerais e metas

A linha de base vem do M-05; as metas relativas valem a partir dela.

| Métrica (`metrics`) | Meta na 0.12 | Meta na 0.13 |
|---|---|---|
| Interrupções humanas por tarefa concluída | −75% em relação à base | −80% |
| Pedidos formais por tarefa concluída | ≤ 1 | ≤ 1 |
| `tool_used` no log assinado | < 50% | < 40% |
| Correções de ator no log | 0 | 0 |
| Erros do check após `migrate` e `--fix` | 0 | 0 |
| Aprovação na 1ª validação | medida | ≥ a da base |
| Benchmark (M-03): testes escondidos, AISEF × puro | publicado | AISEF ≥ puro, com custo de tokens declarado |

**A iniciativa está concluída quando:**
- todas as áreas da seção 3 atingirem a nota-meta numa nova análise, feita com dados de uso real;
- o benchmark estiver publicado;
- a Action `aisef-verify` estiver rodando.

## 9. Marcos

| Marco | Saída | Decisão no marco |
|---|---|---|
| M1: fim da 0.11 | `metrics` com tokens, benchmark rodado, Graphify padrão, linha de base | As metas da seção 8 ganham números |
| M2: fim da 0.12 | Fricção cortada, `migrate`, log em camadas, uso real comparado | Fim do congelamento de funcionalidades |
| M3: fim da 0.13 | Orçamento, worktrees, workflow e perfis | O que fazer com o codebase-memory-mcp (G-05) |
| M4: fim da 0.14 | Action, pacote de evidência, OTel, ADR de streams | Seguir para a 0.15 ou não |
| M5: fim da 0.15 | Vários usuários | Nova análise e notas |

## 10. ADRs previstos

| ADR | Assunto |
|---|---|
| 0020 | Escopo por ferramenta MCP |
| 0021 | Git por risco (substitui o ADR 0004:16) |
| 0022 | Perfis de cerimônia |
| 0023 | Stream de auditoria por pessoa |
| — | Decisão sobre o grafo, ao fim do G-05 |
