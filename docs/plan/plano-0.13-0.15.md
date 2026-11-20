# Plano: da nota 7,5 para 8,5 (0.13 → 0.15)

> **Status:** aprovado, 2026-11-20 (decisões D2–D6 confirmadas pelo usuário).
> **Origem:** análise de 2026-11-20 sobre a 0.12.1 (nota geral 7,5).
> **Relação com o [plano anterior](melhorias-0.11-0.14.md):** este plano **reordena** as tarefas que ainda estão abertas (F-*, L-*, T-*, G-05) e acrescenta tarefas novas (C-*, S-*, H-*, G-06/07, L-06, D-02). Os IDs antigos continuam valendo.
> **Testes e medições ficam fora deste plano.** Como já decidido, o teste de uso real da 0.12 (M-05, portão de revisão, verify-loop, gateway) e as medições do benchmark acontecem depois, no projeto novo que você vai criar. Nenhuma tarefa daqui depende deles.

## 1. Objetivo

Subir primeiro as notas mais baixas que dá para melhorar só com código:

| Dimensão | Hoje | Meta | Peso | Tarefas |
|---|---|---|---|---|
| Usabilidade e adoção (custo, atrito) | 5,5 | 7,5 | alto | C-01…C-05, L-04, F-01, F-03 |
| Graph engineering | 6,5 | 8,0 | médio | G-06, G-07, L-03 |
| Loop engineering | 8,0 | 9,0 | médio | L-01, L-06, L-02 |
| Context engineering | 8,0 | 8,5 | baixo | G-06, G-07 |
| Governança e segurança | 9,0 | 9,5 | médio | F-02, S-01, S-02, F-08 |
| Qualidade de engenharia | 9,0 | 9,5 | baixo | H-01, F-07 |
| Prova de valor (benchmarks) | 4,5 | — | — | fora deste plano: testes no projeto novo |

## 2. Decisões tomadas (2026-11-20: todas na opção recomendada)

| # | Tema | Proposta (recomendada) | Alternativa |
|---|---|---|---|
| D2 | Caminho enxuto (`lean`) | Novo caminho entre o rápido e o completo, **escolhido em código** pela triagem (C-01); você pode sempre forçar o completo | Só documentar quando usar o caminho rápido (não resolve o custo) |
| D3 | Perfis de cerimônia | Fazer a L-04 (solo, team, regulated) junto da triagem, na 0.13 | Manter na ordem antiga, depois do workflow declarativo |
| D4 | Agentes ativos por padrão | Catálogo em dois níveis: **núcleo** (ativado no init) e **estendido** (ativado pela stack ou por pedido) | Manter os 66 disponíveis como hoje |
| D5 | `cryptography` ausente | O init **para** e mostra o comando de instalação, com o doctor dando o comando exato do Python certo. Sem modo sem assinatura | Modo "só cadeia de hash" com aviso permanente (enfraquece a tese do log assinado) |
| D6 | Posicionamento | README em inglês abre pela trilha de evidência para times regulados; a equipe de agentes vira seção | Manter "66 agentes" como manchete |

## 3. Diagnóstico: o que falta para cada nota subir

| Dimensão | O que está faltando (evidência) | Tarefas |
|---|---|---|
| Custo e adoção | Toda feature passa pelo ciclo completo, a não ser que o modelo escolha o caminho rápido. O init pede várias aprovações separadas. Os 66 agentes ficam disponíveis, e não há medida de quais disparam. Pré-requisitos: Python, `cryptography`, Git Bash, às vezes `AISEF_PYTHON` | C-01…C-05, L-04, F-01, F-03 |
| Graph engineering | `aisef_graph.py` só lê o `graphify-out/graph.json`. Sem o Graphify, o `pack` não tem raio de impacto, embora o `aisef_detect.py` já extraia imports de 7 linguagens (`aisef_detect.py:351`). A RTM é um grafo, mas não dá para consultar o impacto de mudar um requisito | G-06, G-07, L-03 |
| Loop | Não há orçamento (`timeout_minutes` nunca é lido). Uma tarefa que falha sempre do mesmo jeito gasta as 3 tentativas subindo de modelo sem aprender nada | L-01, L-06, L-02 |
| Segurança | `gateway.py` classifica comandos com regex sobre a linha inteira (`GIT_RE`, `RM_RECURSIVE_RE`, `OBFUSCATED_RE`…). Não usa `shlex` e não reclassifica o conteúdo de `bash -c "..."`, `eval` nem `$(...)` | F-02, S-01, S-02, F-08 |
| Engenharia | `aisef_project.py` tem 1.281 linhas (log, chaves, pedidos, decisões, ondas, agentes e CLI) e `check_project.py` tem 1.004 | H-01, F-07 |
| Posicionamento | O README abre pela quantidade de agentes. A tese que só o AISEF cobre (evidência assinada mais RTM) aparece só no meio. O roadmap está fora de ordem | D-02, H-02, T-02, T-03 |

## 4. Requisitos

### Funcionais
- Como usuário, eu quero que uma mudança pequena ou de baixo risco custe perto do Claude Code puro sem eu escolher o caminho na mão.
- Como usuário novo, eu quero iniciar o AISEF com poucas aprovações e só com os agentes que a minha stack usa.
- Como orquestrador, eu quero raio de impacto mesmo sem o Graphify e quero saber o que muda quando um requisito muda.
- Como usuário em modo contínuo, eu quero que o loop pare sozinho quando estourar o orçamento ou quando não houver progresso.
- Como responsável por segurança, eu quero que o gateway não seja contornado por aspas, subshell ou `bash -c`.
- Como time regulado, eu quero um pacote de evidência por feature e exportação para as ferramentas que já uso.

### Não funcionais
- **Desempenho:** o gateway continua em torno de 0,2 s por chamada (`tools/bench_hooks.py`); o S-01 pode somar no máximo 20 ms. O grafo nativo (G-06) é montado fora do caminho do hook.
- **Segurança:** falha fechada mantida. Nenhum caminho novo (lean, triagem, perfis) muda o que o gateway permite. Lean e perfis mudam portões do processo, não permissões.
- **Compatibilidade:** Windows (Git Bash) e Linux. Projetos existentes mantêm o comportamento atual até rodarem o `migrate` (F-06).
- **Somente stdlib** no plugin.

## 5. Plano de tarefas

Estimativas em dias de trabalho seu com o Claude, como faixa. **Fechamento de toda tarefa:** testes no `run_tests.py`, docs, CHANGELOG e, quando muda política ou processo, ADR.

### 0.13: Custo, atrito, loop e gateway

```
[x] C-01: Triagem em código e caminho enxuto (lean)
    Status: feito (e9ecc23); o eval triage-choice existe, rodar fica para os testes
    Descrição:
      - Novo core/aisef_triage.py: recebe o pedido já estruturado pelo orquestrador
        (paths prováveis, tipos de mudança) e devolve quick | lean | full com os motivos.
        Sinais, todos em código:
          recurso sensível pelos sensitive_patterns.json (auth, segredo, migração, CI, infra)
          -> full;
          muda API pública, schema de banco ou contrato entre módulos -> full;
          mais de 1 fatia provável ou mais de ~5 arquivos -> full;
          até ~50 linhas, sem mudança de comportamento -> quick (a regra atual, agora em código);
          o resto -> lean.
      - Caminho lean: Feature Contract curto (sem blueprint), uma fatia, TDD exigido,
        só o code-reviewer como revisor, validador no nível mínimo do roteador, RTM completa.
      - O orquestrador mostra a triagem numa linha ("Caminho: lean, porque ...") e você pode
        forçar o full. O check acusa TRIAGE-OVERRIDDEN-DOWN se alguém rebaixar um full.
      - Novo ADR 0023 (complementa o ADR 0009, briefs e caminho rápido).
    Depende de: nenhuma
    Critério de aceite: test_triage com pelo menos 25 casos (cada sinal e as combinações);
      eval novo triage-choice (claude plugin eval) com pedidos de cada caminho.
    Estimativa: 3–4 dias

[x] L-04: Perfis de cerimônia (antecipada do plano anterior, ver D3)
    Status: feito (b2a1d03): init com --profile (padrao solo); regulated com PROFILE-QUICK, PROFILE-TDD e PROFILE-BLUEPRINT
    Descrição: config.profile solo | team | regulated, implementado sobre a triagem da C-01,
      sem esperar o workflow declarativo (L-03):
        solo       triagem ligada; full só quando a triagem pedir;
        team       comportamento atual (full por padrão, triagem só sugere);
        regulated  quick desligado; blueprint, TDD e security obrigatórios em risco alto;
                   check --strict.
      Quando a L-03 chegar, os perfis migram para sobreposições do workflow.
    Depende de: C-01, F-06 (projetos antigos migram para team; sem a F-06, vale só para novos)
    Critério de aceite: test_next e test_triage cobrem os três perfis; o eval feature-choice
      continua passando no solo.
    Estimativa: 2 dias

[x] C-04: Uso dos agentes e catálogo em dois níveis
    Status: feito (2b58904): núcleo de 13 subagentes; qa e doc-updater foram para o estendido
    Descrição:
      - O metrics ganha a seção "Agentes": despachos, tokens e taxa de aprovação por agente,
        a partir dos eventos delegation e do .aisef/runtime/usage.jsonl.
      - O catalog.v0.1.json ganha tier: core | extended. Núcleo proposto: implementer,
        backend, frontend, database, devops, code-reviewer, security, qa, validator, planner,
        architect, code-explorer, doc-updater. O resto é extended e só entra pela stack
        detectada ou por pedido.
      - O init ativa o núcleo mais os agentes da stack, numa aprovação só (C-03).
      - tools/agent_usage.py lê o metrics de vários projetos e lista os agentes que nunca
        dispararam: insumo para a C-05.
    Depende de: nenhuma
    Critério de aceite: num projeto Python novo, no máximo 15 agentes ativos;
      test_catalog cobre o tier; o metrics mostra a seção nos dados do demo.
    Estimativa: 2 dias

[x] G-06: Grafo de imports nativo (fallback do Graphify)
    Status: feito (d8e5d5f): 5.000 arquivos em ~1,2 s
    Descrição:
      - Extrair os regex de import do aisef_detect.py (linha 351) para core/aisef_imports.py,
        usado pelo detect e pelo grafo.
      - aisef_graph.py build-native grava .aisef/runtime/graph.json (gitignored) no mesmo
        formato node-link do Graphify (nós de arquivo, arestas imports), para o related()
        funcionar sem mudança.
      - O pack usa, nesta ordem: Graphify, grafo nativo, nenhum. O context_mode passa a ter
        o valor native.
      - O next sugere reconstruir o nativo nos mesmos marcos da G-03 (é barato e sem modelo).
    Depende de: nenhuma
    Critério de aceite: test_graph cobre Python, TypeScript e C# com raio de impacto correto;
      montar o grafo de um repositório com 5.000 arquivos leva menos de 5 s;
      test_context cobre os três modos.
    Estimativa: 2–3 dias

[x] C-03: Init com uma aprovação em lote
    Status: feito (2e2e531): aisef_setup.py; de quebra, o gateway passou a perguntar ao instalar boas praticas
    Descrição: o aisef-init junta num único pedido (approval-request do tipo setup_bundle)
      os agentes do núcleo e da stack, as regras nativas de segunda camada, as boas práticas
      do estilo detectado e o Graphify, com cada item desmarcável. Hoje cada um é um pedido.
    Depende de: C-04
    Critério de aceite: init num projeto novo com no máximo 3 prompts seus (o eval
      init-trigger confere); recusar um item não quebra os outros.
    Estimativa: 2 dias

[x] C-02: Doctor que resolve o ambiente
    Status: feito (b91db17)
    Descrição: o doctor procura, entre os Pythons do PATH (e py -0p no Windows), um que tenha
      jsonschema e cryptography; se achar, diz o valor exato de AISEF_PYTHON; se não achar,
      mostra o pip install para o Python que o hook usa. Sem modo sem assinatura (D5).
    Depende de: nenhuma
    Critério de aceite: test_doctor com PATH simulado (achou, não achou, vários Pythons).
    Estimativa: 1 dia

[~] F-01, F-03, F-06, F-07, F-08 (do plano anterior, sem mudança de escopo)
    Status: F-06 feito (b2a1d03); faltam F-01, F-03, F-07 e F-08
    F-01 MCP por escopo de ferramenta        2–3 dias
    F-03 Git por risco                        3–4 dias
    F-06 plugin_version e migrate             2–3 dias
    F-07 check --fix e rebase-req             3–4 dias
    F-08 Sandbox nativo recomendado           1 dia

[x] F-02 + S-01: Corpus do gateway e leitura por tokens
    Status: feito: 138 casos, 48 contornos; achou git -c x=y push --force (so perguntava)
    Descrição:
      - F-02 como no plano anterior (corpus em hooks/corpus/*.jsonl, pelo menos 80 casos).
      - S-01: antes dos regex, o gateway divide o comando com shlex (modo posix no sh,
        regras próprias para o PowerShell) em segmentos separados por ; && || | e quebra de
        linha, respeitando aspas. Cada segmento é classificado sozinho e vale o nível mais
        restritivo. Reclassifica o conteúdo de bash -c / sh -c / pwsh -Command, de eval e
        de $(...) e crases. Comando que começa por variável ($X args) ou que o shlex não
        consegue ler vira ask, nunca allow.
    Depende de: nenhuma
    Critério de aceite: corpus com pelo menos 120 casos, sendo 30 tentativas de contorno
      (aspas, subshell, bash -c, eval, variável como comando, alias, quebra de linha), todas
      em ask ou deny; 0 regressões nos casos legítimos; bench_hooks com no máximo +20 ms.
    Estimativa: 4–5 dias

[x] S-02: A chave de assinatura fora do alcance dos agentes
    Status: feito: Grep lia a chave e Edit reescrevia a ancora; agora tudo negado
    Descrição: conferir e garantir que o gateway nega Read, Grep, Glob e qualquer comando de
      shell que toque ~/.aisef/keys e ~/.aisef/anchors (inclusive por caminho relativo,
      variável de ambiente e link simbólico). Casos no corpus da S-01.
    Depende de: S-01
    Critério de aceite: casos de leitura direta, cp, cat via variável, e link simbólico
      negados e registrados no log.
    Estimativa: 1 dia

[ ] F-04: Ciclo de vida registrado pelos hooks (do plano anterior)
    Estimativa: 3–4 dias (confiança média)

[ ] L-01 + L-06: Orçamento e falta de progresso
    Descrição:
      - L-01 como no plano anterior: budget {max_minutes, max_tokens, max_usd,
        max_attempts_total} no Feature Contract, padrões em orchestration-defaults,
        stop_reason budget_exhausted logo depois de critical_risk. Elevar o limite exige
        aprovação. Acrescenta max_usd, calculado pelo metrics.
      - L-06: assinatura de falha por tentativa = hash dos testes que falharam, das regras
        do precheck e dos ids dos achados do revisor e do validador. Duas tentativas seguidas
        com a mesma assinatura param a tarefa com stop_reason no_progress (só essa tarefa;
        a onda segue) e o next pede contexto novo (a recuperação iterativa que a skill já
        descreve) em vez de só subir o modelo.
      - Agente em voo há mais que limits.timeout_minutes vira await_decision com a fonte
        stale_agent.
    Depende de: M-02 (feito), F-04 (para o estado confiável)
    Critério de aceite: test_next cobre tempo, tokens, dólares, tentativas, assinatura
      repetida, assinatura diferente (segue) e agente parado.
    Estimativa: 2–3 dias
```

### 0.14: Grafo do sistema e saúde do código

```
[ ] H-01: Quebrar o aisef_project.py e o check_project.py
    Descrição:
      - aisef_project.py vira um pacote de módulos: audit_log (append, verify, anchor,
        rotate-key), requests (request, decide, reinforced), waves (paths, conflitos,
        compute_waves), agents (contratos, ativação), setup (init, native_settings) e um
        cli.py fino. aisef_project.py fica como fachada com os mesmos subcomandos.
      - check_project.py ganha registro de regras (uma função por grupo, decorada com o id
        da regra), que a F-07 já começa e a L-03 usa.
      - Fazer antes da L-03 e da G-07, que mexem nesses arquivos.
    Depende de: F-07
    Critério de aceite: nenhum módulo com mais de 500 linhas; todos os testes atuais passam
      sem mudança; gen_docs continua em sincronia.
    Estimativa: 3–4 dias

[ ] G-07: Grafo do sistema consultável
    Descrição: aisef_project.py graph query sobre os contratos, sem modelo:
      impact --req REQ-x         tarefas, critérios, testes, arquivos e evidências ligados
      impact --file <caminho>    requisitos e tarefas que tocam o arquivo
      why --task T-x             requisitos, decisões e ADRs que justificam a tarefa
      Usado pelo rebase-req (F-07), pela reabertura de feature e pelo pack.
    Depende de: H-01
    Critério de aceite: test_graph_query sobre o demo; o painel de Rastreabilidade ganha o
      filtro "impacto de".
    Estimativa: 2–3 dias

[ ] L-03: Workflow declarativo (do plano anterior)
    Observação: os perfis da L-04 passam a ser sobreposições do workflow.
    Estimativa: 3–5 dias

[ ] F-05, F-09, L-02a, L-02 (do plano anterior, sem mudança de escopo)
    F-05 Log em camadas                       2–3 dias
    F-09 Custo de atenção no painel           1–2 dias
    L-02a Raiz do projeto via git-common-dir  1–2 dias
    L-02 Worktrees por fatia                  4–6 dias (confiança baixa a média)

[ ] C-05: Revisão do catálogo com dados
    Descrição: com o C-04 rodando em projetos reais, juntar ou remover agentes que nunca
      dispararam; decisão sua, uma linha por agente.
    Depende de: C-04 e uso real
    Critério de aceite: lista revisada e aplicada no catalog.v0.1.json, com nota no CHANGELOG.
    Estimativa: 0,5 dia
```

### 0.15: Times e mercado

```
[ ] D-02: Reposicionamento
    Descrição: README em inglês e em português abrem pela tese "trilha de evidência para
      engenharia com IA": o que só o AISEF cobre (regra aplicada em código, log assinado,
      RTM até a evidência) e para quem é (times regulados e quem precisa provar o que a IA
      fez). A equipe de agentes vira uma seção. Quando os testes no projeto novo tiverem
      números, eles entram aqui.
    Depende de: T-02
    Estimativa: 1 dia

[ ] H-02: Documentação sincronizada
    Descrição: roadmap.md em ordem de versão e com o que este plano mudou; gen_docs passa a
      conferir que o roadmap cita todas as versões do CHANGELOG.
    Depende de: nenhuma (pode sair a qualquer momento)
    Estimativa: 0,5 dia

[ ] T-01, T-02, T-03, T-04, T-05 (do plano anterior, sem mudança de escopo)
    T-01 GitHub Action aisef-verify           3–4 dias
    T-02 Pacote de evidência (SOC 2, ISO)     2–3 dias
    T-03 Exportação OTel                      2 dias
    T-04 Spike do stream por pessoa           3–4 dias
    T-05 Streams por pessoa                   5–8 dias
```

## 6. Metas mensuráveis

Todas conferidas por teste automatizado ou eval, sem depender do teste de uso real.

| Dimensão | Meta | Como conferir |
|---|---|---|
| Adoção | No máximo 3 prompts no init e no máximo 15 agentes ativos num projeto Python | eval `init-trigger`, `test_catalog` |
| Custo | Triagem correta nos 25 casos do `test_triage` e no eval `triage-choice` | C-01 |
| Graph | Raio de impacto disponível sem o Graphify; consulta de impacto de requisito e arquivo | G-06, G-07 |
| Loop | O loop para por orçamento e por falta de progresso, com teste para cada caso | L-01, L-06 |
| Segurança | 0 contornos conhecidos permitidos em pelo menos 120 casos do corpus | S-01 |
| Engenharia | Nenhum módulo do núcleo com mais de 500 linhas | H-01 |

## 7. Ordem recomendada dentro da 0.13

```
bloco 1   C-01 (triagem e lean)  ·  C-04 (uso dos agentes)  ·  G-06 (grafo nativo)  ·  C-02 (doctor)
bloco 2   L-04 (perfis)  ·  C-03 (init em lote)  ·  F-02 + S-01 (gateway)  ·  F-06 (migrate)
bloco 3   S-02  ·  F-01  ·  F-03  ·  F-04  ·  F-07  ·  F-08  ·  L-01 + L-06
```

C-01, C-04, G-06, C-02, F-02/S-01 e F-06 não dependem de nada e podem começar juntos. A C-01 é o maior risco de produto (errar a triagem barateia demais uma mudança perigosa); por isso o perfil `team` mantém o comportamento atual e o check acusa rebaixamento de full.

## 8. Riscos

| Risco | Efeito | Mitigação |
|---|---|---|
| A triagem rebaixa uma mudança sensível | Mudança arriscada com menos cerimônia | Sinais de recurso sensível sempre forçam full; o gateway não muda; check `TRIAGE-OVERRIDDEN-DOWN`; perfil `team` mantém o comportamento atual |
| O S-01 bloqueia comandos legítimos | Mais prompts, mais atrito | Corpus com casos legítimos e meta de 0 regressões; o que o shlex não lê vira ask, não deny |
| O H-01 quebra a CLI | Projetos e skills chamam subcomandos que mudaram | `aisef_project.py` fica como fachada com os mesmos subcomandos; todos os testes atuais passam sem mudança |
| O catálogo enxuto esconde um agente útil | Menos cobertura de revisão numa stack | Os agentes da stack detectada entram sempre; os estendidos podem ser ativados por pedido; a C-05 só remove com dados de uso |
