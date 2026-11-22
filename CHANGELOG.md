# Changelog

## Não lançado

### Outra sessão no mesmo projeto: detecção e coordenação
Duas sessões do Claude Code no mesmo projeto (mesma pasta ou worktrees) refaziam o trabalho uma da outra sem saber, e um `git add -A` podia levar o trabalho da outra para o commit. Agora cada sessão deixa um registro em `.aisef/runtime/sessions/` (fora do Git; worktrees gravam no projeto principal), com batimento pelo gateway e os arquivos editados pela auditoria (`core/aisef_sessions.py`).
- **Áreas separadas.** Cada sessão reserva a sua área (`aisef_sessions.py claim`); ao disparar uma fatia, a reserva é automática (`scope.paths_allowed` + `exclusive_files`) e é solta quando o executor entrega. Quando aparece outra sessão, ou a área dela muda, o gateway avisa as demais (uma vez por mudança) para ficarem fora dela e reservarem a sua; `claim` sobre uma área já reservada sai 3 para combinar com o usuário.
- **Barreira.** Editar na área reservada por outra sessão, ou num arquivo que ela tem alterado sem commit, faz o gateway perguntar, dizendo quem, onde e como ver o diff.
- **Antes de commit, push, PR ou merge**, o gateway mostra as mudanças sem commit das outras sessões (arquivos, branch, diffstat e `git -C <pasta> diff HEAD`), inclusive na mesma pasta. As worktrees das fatias da própria sessão não contam; o que já foi commitado lá, ou está esquecido há dias sem sessão, não incomoda.
- O doctor avisa no início da sessão; `aisef_sessions.py status --diff` mostra tudo; a skill `aisef` explica o procedimento.

### Painel com informação certa e mais fácil de ler
Veio do uso real (HireMe, 8 features e mais de 2.000 eventos no log): o painel mostrava features aceitas como "Aprovada p/ execução", misturava fatias de features diferentes nas mesmas ondas, acendia alarme vermelho em fatias já concluídas e contava zero trabalho para revisores e validador.
- **Feature aceita aparece como aceita.** O estado vem do pedido `feature_acceptance` mais recente da feature: aceite aprovado com todas as fatias encerradas vira "Aceita" (com a data) e a etapa "Encerrada" fica concluída, mesmo com o contrato ainda em `approved_for_execution`. Aceite recusado e alterações pedidas aparecem como tal; fatias encerradas sem aceite decidido viram "Aguardando aceite", e feature com fatia já despachada vira "Em execução". Campos novos `effective_status` e `accepted_at` em `features` (opcionais no schema). Em Features e fatias, as aceitas ficam recolhidas num bloco.
- **Mapa dos agentes refeito.** Um seletor de feature no topo da tela comanda os três blocos (sem escolha: as features em andamento; sem nenhuma, a visão geral com uma linha por feature, e o clique foca nela). Cada agente registrado vai para a fatia em que trabalhou (o `task_id`, o que valida ou a fatia citada na descrição, como "Validar onda: T-017"); sem fatia, para a feature citada ("FEAT-005 review"), no fechamento dela; sem nenhuma, "fora de feature". A fase vem do papel: executar, revisar, validar ou apoio.
  - **Mapa de execução:** as ondas da feature em colunas (com a data do despacho) e cada fatia num cartão com estado, duração e os agentes que trabalharam nela em pílulas por fase, sempre com a contagem ("2 executores", "8 revisores"; com três fases ou mais, o nome curto: "4 exec · 9 rev · 3 valid"); a pílula abre o agente. As setas são as dependências, e a última coluna é o fechamento (revisão final e aceite). Some o nó solto do orquestrador e os selos flutuantes. Novo `live.board.feature_waves`.
  - **Em paralelo vira linha do tempo:** uma raia por fatia da feature em foco (e uma pelo fechamento), cada barra é um agente colorido pela fase, e agentes simultâneos empilham na raia. Os períodos sem atividade (mais de 20 min, medidos pelas ações dos agentes, não pela barra inteira) viram um corte hachurado com a duração, então dois dias de trabalho cabem sem virar pontinhos; a escala se ajusta à largura e a rolagem abre no mais recente. Na visão geral, uma raia por feature com uma subfaixa por fase. Acabam as 30 raias chamadas só "validator". Sem os hooks de subagente, a raia usa os períodos da própria fatia.
  - **Quem disparou quem:** orquestrador > feature (recolhível, aberta a que está em foco) > fatia > agentes em ordem de início, com hora, papel, o que fez e duração; subagente fica embaixo de quem o disparou. O comando bruto saiu da lista e fica na gaveta do agente.
  - **Visão geral em cartões:** uma grade com um cartão por feature: estado, título, as ondas em quadradinhos coloridos pelo estado de cada fatia até o aceite, fatias concluídas, agentes, duração e uma barra com os agentes por fase. O clique abre o fluxo da feature.
  - **Gaveta maior e legível:** até 560 px de largura, fundo opaco, texto de 14 px, título inteiro, ações e passos sem corte, e os agentes da fatia agrupados por fase com hora de início e duração.
  - **Barras de rolagem** finas e na cor do tema, no claro e no escuro.
  - A fase do agente vem primeiro do papel e só depois da descrição: um executor com "revisão" na descrição não conta mais como revisor.
- **Alarme do gateway só quando pesa.** A negação vira selo vermelho só quando a fatia está ativa (rodando, validando, esperando você ou reprovada) e nada aconteceu depois dela. Nas demais, o nó ganha um ícone neutro discreto e a gaveta mostra o histórico (quantas, a última, o motivo); nas raias, as negações antigas ficam em cinza.
- **Agentes: trabalho pelo papel real.** A contagem vem dos relatórios: fatias executadas, revisadas e validadas (campo `work` em `agents`), em vez de "0 fatia(s) atribuída(s)" para revisores e validador. Status traduzido ("ativo · livre"), id sem repetir o papel, agentes sem trabalho recolhidos. Agente sem `SubagentStop` parado há mais de 2 h, ou cuja fatia já terminou, deixa de contar como rodando (`end_missing`), e start repetido do mesmo agente não duplica a linha.
- **Histórico legível.** "2.178 eventos" e "sequência #2177" em vez de números que pareciam anos; linha do tempo agrupada por dia ("Hoje, sábado, 21/11"); o id não se repete no texto; negação do gateway mostra o motivo e o comando resumidos (campo `detail` na linha do tempo); hash e prev ficam sob demanda ("Mostrar hashes"), com o número do evento discreto. O selo do topo diz "evento #N".
- **Cards do mapa.** Título em até 2 linhas com reticências e o título inteiro ao passar o mouse; duração explícita ("levou 21 min", "há 12 min"); horários com data quando não são de hoje, também na gaveta e nas raias.
- **Custo de atenção explicado.** Mostra a composição (pedidos de aprovação + perguntas do gateway, com barra), "6,3 interrupções por tarefa (139 ÷ 22 tarefas concluídas)", o que significa "aprovadas de primeira" e uma nota sobre o que conta como interrupção.
- **Faixa de estados.** Mostra até 3 ids e "+N · ver todas"; o clique filtra e leva à tabela de fatias.
- **Engenharia.** Seletor de blueprint (padrão: o mais recente), em vez dos blueprints empilhados; o card de endpoints só aparece quando há endpoints; sem ligações entre componentes, eles aparecem em cartões em vez de um diagrama de caixas soltas.
- **Governança.** Sem decisão pendente, uma faixa compacta substitui a coluna vazia; Decididas ganha filtro por tipo e por feature (que também filtra decisões e riscos) e "Ver todas" (lista completa em `approvals.decided`).
- **Rastreabilidade.** Requisitos agrupados por feature (aceitas recolhidas), sem o id repetido; a evidência usa só o relatório do executor e explica o caso sem testes ("sem testes automatizados · 3 critérios atendidos", com "validada" quando há validação independente). Execuções ganham `kind` e `agent_id`.
- **Coluna TDD com 0/0 em toda fatia revisada.** A contagem guardava só o último relatório lido da tarefa, e os relatórios de revisor e validador (sem ciclos) zeravam o que o executor registrou. Agora os ciclos somam entre as tentativas do executor e relatórios sem ciclos não contam (`tdd_counts`).
- **Última ação sem o `cd <pasta> &&` do início.** Na equipe, no mapa e na gaveta, o caminho local do projeto não empurra mais o comando útil para fora da linha.
- **Favicon embutido** (data URI): acaba o 404 de `/favicon.ico` no console. O seletor de feature não estoura mais a largura no celular.
- **Painel: arrastar para navegar.** O mapa de execução e as raias "Em paralelo" rolam segurando o botão esquerdo do mouse e arrastando (a mão aparece quando há o que rolar). Um arrasto não vira clique, então o clique simples num nó continua abrindo a gaveta; o toque segue com a rolagem nativa; a atualização ao vivo espera o arrasto terminar. Coberto pelo autoteste no Chrome.

### Repositório sem commit e limpeza de branch sem remoto
Também veio do uso real (HireMe): o projeto tinha `git init`, mas nenhum commit, e o verify pulou a varredura de segredos e o diff sem que ninguém avisasse.
- **Verify sem commit.** A varredura de segredos e o resumo do diff não pulam mais num repositório sem commit: comparam com a árvore vazia, o que cobre tudo que está no index (o que o commit inicial levaria). Antes, o commit inicial, o que mais leva `.env` e chave, passava sem varredura nenhuma.
- **Ação `first_commit` no `next`.** Quando o repositório existe e não tem nenhum commit, o `next` mostra a ação com os comandos (`git add -A`, varredura de segredos do verify no index, commit) e o pedido de aprovação (`git_operation commit`). É só aviso, como o `setup_remote`: não conta como trabalho pendente e não impede o `stop_reason`. O doctor avisa o mesmo no início da sessão (`commit_advice`).
- **`git_state` sem commit.** Passa a devolver `has_head` e a branch real pelo HEAD simbólico (`symbolic-ref`), em vez de `"HEAD"`.
- **Limpeza de branch sem remoto.** Sem o remote do `git.remote`, `delete_merged_branch` sugere só a exclusão local (`git branch -d`) e pede o merge local em `base_branch` (`git branch --merged`), em vez de `git push --delete` e do merge do PR.
- As skills `aisef-init` e `aisef` explicam as duas situações.
- **Mapa de agentes: subagente na onda errada.** O `match_parents` ligava cada `SubagentStart` ao disparo livre mais antigo do mesmo papel. Um disparo que nunca virou start (negado, cancelado), ou que foi gravado depois do seu start (o hook do disparo era assíncrono), ficava livre para sempre, e cada subagente seguinte do mesmo papel herdava o disparo anterior: caía na coluna de uma fatia antiga, com a hora de despacho de outra onda, e o hook podia gravar `task_started` da fatia errada no log. Agora o disparo só vale perto do start (até 5 min antes, 1 min depois), e o hook do disparo (PreToolUse `Agent|Task`) é síncrono.

## 0.15.5: repositório remoto conferido antes do primeiro push
Veio do uso real: no projeto de teste, os pushes não funcionavam porque ninguém conferiu se o projeto tinha repositório no GitHub.
- **`next` com a ação `setup_remote`.** Quando o projeto usa o fluxo de branch (`git.branch_per_feature` ou `git.delete_branch_after_merge`) e não é repositório Git, ou não tem o remote, o `next` mostra a ação com:
  - o `check` (`gh repo view <nome>`);
  - o `if_exists` (`git remote add`);
  - o `if_missing` (`gh repo create --private --source . --remote origin`);
  - sem repositório, também o `git init -b <base>`.

  É só um aviso: não conta como trabalho pendente e não impede o `stop_reason`. O `git_state` passa a ler a URL do remote, sem rede.
- **Doctor avisa no início da sessão.** Avisa quando o repositório não tem o remote, ou quando não é repositório Git mas o fluxo de branch está ligado. O aviso manda perguntar ao usuário se o projeto já existe no GitHub antes de criar outro.
- **aisef-init e aisef.** O init confere o repositório e o remote antes de qualquer commit, e nunca supõe que o repositório não existe: pergunta ao usuário o dono e o nome e confere com `gh repo view`.
- **Gateway: remoto é decisão do usuário.** `git remote add/set-url/remove/rename` e `gh repo create/delete/rename/edit/archive/fork` viram a operação nova `remote_config` (`approve_operation`), na política e nos schemas. Antes, os dois passavam sem perguntar. `git remote add` também deixou de contar como leitura no modo Ask. `git ls-remote` passou a ser leitura e não pergunta mais. O corpus ganhou 6 casos (144).

## 0.15.4: coluna da direita na altura do artefato
- **Um bloco só não estica mais.** Na tela Agora, quando a coluna da direita tem um bloco só (sem decisão pendente, só o custo de atenção), ele fica com metade da altura do mapa (cerca de 290 px), a mesma de quando há dois blocos, como no artefato aprovado. Antes, ele esticava até os 600 px do mapa e ficava com um vazio grande. Com dois ou mais blocos, eles continuam dividindo a altura em partes iguais.

## 0.15.3: tempo ativo e mapa com altura fixa no painel
- **Tempo ativo no topo.** No modo ao vivo (`--serve`), o indicador passa a mostrar há quanto tempo o painel está aberto ("ao vivo · ativo há 12 min"). Antes, ele mostrava o tempo desde a última leitura do servidor, que volta a zero a cada 3 s e por isso ficava sempre em "há 0–3 s". A hora em que o painel abriu e a última leitura ficam no texto que aparece ao passar o mouse. O texto também deixou de sumir entre 761 e 1180 px de largura.
- **Os tempos decorridos andam sozinhos.** "Rodando há", "esperando você há" e os tempos do mapa e das raias congelavam entre uma mudança e outra do `.aisef/`. No modo ao vivo, o painel agora redesenha a cada 30 s quando nada mudou, mantendo a rolagem (também a vertical), os detalhes abertos e a gaveta. Isso não acontece se você estiver digitando, selecionando texto ou com o zoom ou a busca abertos.
- **Mapa de execução com altura fixa (600 px).** Na tela Agora, com duas colunas, o mapa tem altura fixa e rola por dentro. Os blocos da direita (decisões pendentes e custo de atenção) dividem essa altura em partes iguais, e cada um rola por dentro quando o conteúdo não cabe. O link "Ver as N decisões" fica com a altura natural. Com uma coluna (até 1100 px), nada muda.

## 0.15.2: maturidade, combinações de modos e números do README
- **Teste de combinações de modos (H-04).** Novo `core/test_modes.py`, com git de verdade. Roda o ciclo inteiro de uma feature em 48 combinações: perfil (solo, team, regulated) × pedido (pequeno, com comportamento) × paralelismo (`paths`, `worktree`) × telemetria (`split`, `signed`) × log por pessoa (desligado, ligado). O ciclo passa por triagem, contrato ou caminho rápido, aprovação, despacho, edição pelo hook de auditoria, relatório com TDD, revisores, validação e conclusão. Depois rodam todos os leitores: check, verify do log, next, metrics, painel, grafo do sistema, OpenTelemetry, pacote de evidência e CI. Em cada combinação, o teste confere que:
  - o log verifica e o check não acusa erro;
  - cada evento cai onde o modo manda: no stream de quem executou ou no log do dono, na telemetria ou no log assinado;
  - os leitores veem o mesmo ciclo;
  - o caminho e a onda seguem o perfil e o paralelismo.

  São 772 verificações, e nenhuma combinação mostrou defeito.
- **Tabela de maturidade (`docs/reference/maturity.md`).** Para cada recurso da 0.13 em diante, a tabela diz se já rodou em uso real ou só no CI, se vem ligado e como voltar atrás. Por enquanto, todos estão no nível CI. O `gen_docs --check` falha quando o CHANGELOG cita um ID que não está na tabela.
- **Números do README conferidos (H-03).** O `gen_docs --check` compara com o código, nos dois idiomas, as regras do check, os casos e contornos do corpus do gateway, os agentes (total, núcleo e projeto Python) e as boas práticas. A seção de novidades fica de fora. As verificações viram um piso arredondado (**2.500+**), que o `run_tests.py` compara com o total medido: o piso não pode passar do total nem ficar mais de 10% abaixo dele.

## 0.15.1: painel com custo de atenção e impacto
- **Custo de atenção na tela Agora (F-09).** Novo card na coluna da direita com interrupções (pedidos ao Approval Center mais prompts do gateway), interrupções por tarefa concluída, taxa de aprovação na 1ª validação e mediana de tokens por tarefa concluída. Os dados saem do `build_panel.py` (`attention` no `panel-data`), com a mesma conta do `metrics`.
- **Filtro "Impacto de" na Rastreabilidade (G-07).** Digite um requisito, uma tarefa ou um arquivo (aceita `\` e `./`) e a tela mostra só os requisitos ligados a ele, pelo escopo das tarefas e pelos arquivos que os relatórios mudaram (`files` em cada linha da RTM). O filtro sobrevive a recarregar.
- **Tela Agora mais limpa.** O bloco "Próximo passo" saiu da coluna da direita, e o mapa de execução acompanha a altura dela, com as faixas das ondas até a legenda.

## 0.15.0: times e auditores ([plano](docs/plan/plano-0.13-0.15.md))
- **Um log por pessoa (T-04 + T-05, [ADR 0026](docs/adr/0026-log-por-pessoa.md)).** Com `aisef_streams.py enable` (decisão do usuário), o log atual vira o stream do dono, sem reescrever nada.
  - **Stream de cada pessoa:** fica em `.aisef/audit/streams/<id>/`, com cadeia, `log_id`, chave Ed25519, ids de evento e `head.json` próprios. A identidade vem do `AISEF_USER` ou do e-mail do Git.
  - **Merge sem conflito:** cada pessoa só anexa aos próprios arquivos, então o merge do Git não conflita no log.
  - **Decisões:** aprovações e aceites saem assinados pela chave de quem decidiu.
  - **Leitura:** os leitores recebem os streams juntos, em ordem de tempo.
  - **Verificação:** o `verify`, o painel e a Action verificam stream a stream; o check usa a posição para a ordem das correções e confere o tempo dentro de cada stream. Na PR, apagar ou cortar o stream de alguém é pego.
  - **Sem streams, nada muda.** Teste com git de verdade, duas pessoas e um merge em `core/test_streams.py` (17).
- **Exportação OpenTelemetry (T-03).** Novo `core/aisef_otel.py export --out traces.json`, que gera OTLP/JSON sem modelo e sem rede, para enviar a um coletor OTLP/HTTP ou importar num backend:
  - um trace por feature, com id estável entre exportações;
  - span raiz da feature, com as decisões do usuário e do gateway como eventos;
  - um span `invoke_agent <papel>` por tentativa, seguindo as convenções GenAI do OTel (`gen_ai.operation.name`, `gen_ai.agent.name`, `gen_ai.request.model`, `gen_ai.usage.*` vindos do `usage.jsonl`) mais `aisef.*` (tarefa, tentativa, nível e resultado, com status de erro na reprovada);
  - spans filhos `execute_tool <ferramenta>` para as chamadas do subagente, do log e da telemetria.

  As convenções GenAI ainda estão em desenvolvimento no OTel; `gen_ai.provider.name` não é usado porque saiu dos spans internos de agente. Testes em `core/test_otel.py` (12).
- **Pacote de evidência por feature (T-02).** Novo `core/aisef_evidence.py build --feature --out` junta, numa pasta:
  - Feature Contract (requisitos, spec, RTM, triagem), Task Contracts, Execution Reports e os pedidos do Approval Center;
  - os eventos assinados da feature, completos, e as chaves públicas;
  - o resultado do verify do log e do aisef-check;
  - uma tabela de controles com o status calculado e onde está cada evidência: SOC 2 CC8.1 (gestão de mudanças) e ISO/IEC 27001:2022 A.8.32 (gestão de mudanças) e A.5.3 (segregação de funções).

  O pacote se verifica sozinho, sem o projeto (`verify --pack`): o `manifest.json` tem o sha256 de cada arquivo, e cada evento tem o hash recalculado e a assinatura Ed25519 conferida com a chave do pacote. Um evento adulterado é pego mesmo que o manifesto seja refeito. É material para o auditor, não certificação. Testes em `core/test_evidence.py` (12).
- **GitHub Action `aisef-verify` (T-01).** Composite action em `.github/actions/aisef-verify/`, que roda o novo `core/aisef_ci.py`, só com as chaves públicas. A Action falha quando:
  - o log assinado não confere (cadeia de hash, Ed25519 e o `head.json` versionado);
  - o aisef-check acusa erro (com `strict`, também aviso);
  - no modo PR, o log não contém mais o último evento da branch base com o mesmo hash. Isso pega o corte do fim do log com um `head.json` antigo restaurado, que tem assinatura válida;
  - no modo PR, a PR toca uma tarefa (pelo contrato ou por um arquivo do escopo) que está executada e não validada.

  O resumo em markdown vai para o job summary. O CI do próprio repositório roda a Action sobre o projeto de demonstração. Testes com git de verdade em `core/test_ci.py` (11). Para usar em outro repositório: `uses: NowItMakesSense/aisef/.github/actions/aisef-verify@main`, com `fetch-depth: 0` no checkout.
- **README reposicionado (D-02).** Em inglês e em português, o README abre pela trilha de evidência: o que só o AISEF cobre (regra aplicada em código, log assinado e por pessoa, rastreabilidade até a prova, verificação em cada PR, pacote para o auditor, OpenTelemetry) e para quem ele é. A equipe de agentes virou uma seção, com núcleo e estendido, e os números foram atualizados (166 regras, 1.818 verificações, 138 casos do gateway).
- **Roadmap em ordem e conferido (H-02).** `docs/roadmap.md` separa as próximas versões das entregues, em ordem, e o `tools/gen_docs.py --check` (que roda no `run_tests.py`) falha quando uma versão do CHANGELOG não aparece no roadmap.

## 0.14.0: grafo do sistema, workflow declarativo, log em camadas e worktrees ([plano](docs/plan/plano-0.13-0.15.md))
- **Worktree por fatia (L-02).** Com `config.json` → `"parallel": {"mode": "worktree"}`, fatias com arquivos em comum entram na mesma onda, cada uma no seu worktree (`.aisef/worktrees/<T>`, branch `slice/<feature>/<T>`, fora do Git). O `next` e o `dispatch` trazem o comando de criar o worktree, e o prompt manda o agente trabalhar e commitar lá. O `complete` traz os comandos de integrar. No gateway:
  - são livres (`worktree_local`): `git worktree`, `git branch -d` de `slice/*` já integrada, `git merge --abort` e trazer a branch da feature para a fatia;
  - o merge da fatia na branch da feature é `git_feature_branch`/`merge`, coberto pelo mesmo escopo do push;
  - commit na branch da fatia é livre;
  - um único `cd` ou `git -C` para dentro do projeto passa a revelar a branch, em vez de deixá-la desconhecida;
  - `-D` continua reforçado, e push da fatia continua pedindo.

  Conflito no merge vira `task_rejected` com `merge_conflict`, e a nova tentativa reaproveita o worktree. O padrão continua `paths`. Regra nova `CONFIG-PARALLEL` e migração `0.14-worktrees-ignore`. Teste de ponta a ponta com git de verdade em `core/test_slices.py` (24): duas fatias no mesmo arquivo, a primeira integra e a segunda conflita.
- **Worktree grava no `.aisef` principal (L-02a).** `aisef_git.aisef_root` lê o `.git` do worktree (`gitdir:` e `commondir`), sem subprocesso, e todos os hooks (gateway, auditoria, subagentes, doctor, nudge do grafo, modo Ask) e a CLI do `aisef_project` passam a usar o `.aisef` do repositório principal. Assim, um agente num worktree não divide o log assinado, as aprovações nem o runtime. Testado com `git worktree add` de verdade (`core/test_worktree.py`, 10).
- **Custo de atenção como métrica (F-09, parte de cálculo).** O `metrics` ganha `interruptions`: quantas vezes o usuário precisou parar (pedidos ao Approval Center mais prompts do gateway), no total e por tarefa concluída. O card na tela Agora do painel fica para uma prévia do desenho, como manda a regra de interface.
- **Log em camadas (F-05).** Novo `core/aisef_telemetry.py`. Com `config.json` → `audit.telemetry = "split"` (padrão dos projetos novos), as edições de arquivo e as chamadas MCP liberadas vão para `.aisef/telemetry/telemetry.jsonl`: cadeia de hash própria (alteração e remoção são detectadas), sem assinatura, fora do Git, com rotação e a mesma trava do log. O log assinado fica com o ciclo de vida, as decisões, os comandos de shell (de onde sai o consumo da aprovação reforçada) e tudo o que o gateway negou ou perguntou. Numa feature típica, `tool_used` passa a ser menos da metade do log assinado. Projetos antigos continuam em `signed` até o `migrate` (nova migração `0.14-telemetry`). O `metrics` conta a telemetria à parte, e o check ganha o aviso `TELEMETRY-CHAIN`. Testes em `core/test_telemetry.py` (16).
- **Workflow declarativo (L-03).** O fluxo do AISEF virou dado, numa fonte só: `core/workflow.v0.1.json`, com schema próprio. O arquivo guarda os estados da tarefa e a ordem deles, cada evento com o estado que produz e quem o registra, as fases com os passos e os portões, os tipos de pedido do Approval Center e os perfis de cerimônia. Passam a ler dele: o `next` (estado efetivo), o guia de fases, a triagem, o `aisef_new` (caminho rápido) e o check (`PROFILE-*`). Nada mudou de comportamento: os valores eram idênticos e a suíte inteira passa. Novo `core/aisef_workflow.py check|show`, que confere a coerência (evento com estado que existe e que está no log de auditoria, cada tipo de pedido com o seu portão, perfis iguais aos aceitos no config). Os perfis da L-04 viraram sobreposições do workflow. Testes em `core/test_workflow.py` (20).
- **Grafo do sistema consultável (G-07).** Novo `core/aisef_sysgraph.py`, sem modelo: `impact --req` (tarefas, critérios, testes, arquivos do escopo e dos relatórios, evidências e elementos do blueprint), `impact --file` (requisitos e tarefas que tocam o arquivo, pelo escopo ou pelo que os relatórios registraram) e `why --task` (requisitos com origem, decisões, ADRs, blueprint e caminho da triagem). A reabertura de feature começa a Impact Analysis por ele, e o `rebase-req` aponta para ele quando uma tarefa iniciada fica bloqueada. Testes em `core/test_sysgraph.py` (16). O filtro "impacto de" no painel fica para quando houver o desenho aprovado da tela.
- **Módulos menores, sem mudar comportamento (H-01).** Nenhum módulo do núcleo e dos hooks passa de 500 linhas (antes: `aisef_project.py` 1.300 e `check_project.py` 1.141):
  - `aisef_project.py` virou fachada com a CLI; o código foi para `aisef_base`, `aisef_audit_log`, `aisef_agents`, `aisef_requests` e `aisef_waves`. Quem faz `import aisef_project` continua igual;
  - a `check()` do check virou um registro de grupos de regras (`check_project.RULE_GROUPS`) em `check_rules_1..3.py`, com as regras sem mudança (a referência de regras gerada ficou idêntica);
  - `gateway.py` → `gateway_rules.py` (padrões e classificação), `aisef_context.py` → `aisef_context_aux.py`, `build_panel.py` → `panel_mermaid.py`, `aisef_next.py` → `aisef_guide.py`, `aisef_detect.py` → `aisef_detect_rules.py`, `aisef_new.py` → `aisef_rebase.py`. Cada original reexporta o que saiu. Latência do gateway igual (mediana 154 ms).

## 0.13.0: custo, atrito, loop e gateway ([plano](docs/plan/plano-0.13-0.15.md))
- **Grafo nativo de imports (G-06).** Sem o Graphify, o pacote de contexto passa a ter raio de impacto mesmo assim:
  - novo `core/aisef_imports.py` (fonte única dos regex de import, também usada pelo radar) resolve cada import para o arquivo do repositório em Python, TypeScript/JavaScript, Java/Kotlin, C#, Go, PHP, Ruby, Dart e Rust; import ambíguo demais é descartado, e biblioteca externa fica de fora;
  - `aisef_graph.py build-native` grava `.aisef/runtime/graph.json` (fora do Git) no formato do Graphify, e o `pack` o reconstrói sozinho quando um arquivo de código muda, entra ou sai;
  - o `pack` usa, nesta ordem, o Graphify, o grafo nativo e nenhum. O `context_mode` ganha o valor `native`;
  - 5.000 arquivos em cerca de 1,2 s; conferir que nada mudou leva cerca de 0,2 s. Testes em `core/test_graph.py`.
- **Catálogo em núcleo e estendido (C-04).** Um projeto Python novo começa com 15 agentes, não 33:
  - campo `tier` no catálogo: os papéis `always` são o núcleo (13 subagentes: executores, `code-reviewer`, `database-reviewer`, `pr-test-analyzer`, `security`, `validator`, `planner`, `architect`, `code-explorer`); com `tier: extended` (qa, doc-updater, e2e-runner, code-simplifier, refactor-cleaner, performance-optimizer, spec-miner, docs-lookup, commit-reviewer e outros) só entram por pedido (`agents --roles`);
  - o `architecture-reviewer` entra quando um estilo de arquitetura é detectado ou adotado;
  - projetos existentes não mudam: contratos já criados continuam;
  - `metrics` ganha a seção **Agentes**: tarefas, despachos e 1ª validação por executor, vereditos por revisor, execuções e tokens por papel, e os contratos ativos que nunca trabalharam;
  - novo `tools/agent_usage.py`: soma vários projetos e lista os papéis nunca usados (insumo da revisão do catálogo, C-05).
- **Triagem em código e caminho enxuto (C-01, [ADR 0023](docs/adr/0023-triagem-em-codigo-e-caminho-enxuto.md)).** A escolha entre caminho rápido e ciclo completo saiu do modelo:
  - novo `core/aisef_triage.py` devolve `quick`, `lean` ou `full` com os motivos. Força `full`: recurso sensível pela classificação do gateway, migração, auth, tipos `api`/`schema`/`security`/`ci`/`infra`/`dependency_breaking`/`public_contract`/`cross_module`, risco alto, mais de uma fatia, mais de 5 arquivos ou tamanho desconhecido;
  - **caminho `lean`**: Feature Contract curto, uma fatia com TDD, sem blueprint, só o `code-reviewer`, validador independente e RTM completa. O brief leva a saída da triagem em `"triage"`, e o contrato a guarda;
  - perfil no `config.json`: `solo` usa a triagem; `team` (padrão sem perfil) só sugere o lean; `regulated` desliga o caminho rápido;
  - só se sobe de caminho: o `aisef_new` recusa descer, e o check ganha `TRIAGE-OVERRIDDEN-DOWN` e `TRIAGE-LEAN-SHAPE`;
  - skills `aisef` e `aisef-feature` (nova fase 0, Triagem) e eval `triage-choice`. Testes em `core/test_triage.py` (54).
- **Gateway lê comandos por tokens (S-01) e tem corpus de testes (F-02).** Novo `hooks/shell_parse.py`: além da linha original, o gateway classifica cada segmento sem aspas nem escapes e o que vai dentro de `bash -c`, `pwsh -Command`, `cmd /c`, `eval`, `$(...)`, crases, subshell, heredoc que alimenta um shell e prefixos (`env`, `sudo`, `nohup`, `timeout`, `xargs`...). Também classifica as strings de código inline (`python -c`, `node -e`). O pior nível vence, então nada afrouxa. Comando que vem de variável (`$X args`, `& $x` no PowerShell), `-EncodedCommand` e aspas sem fechar viram pergunta. `$AISEF_PYTHON` e `$PYTHON` contam como python. O corpo de heredoc é dado, não comando.
  - Contornos que passavam: `g"i"t push`, `bash -c "git push"`, `python -c "os.system('git push')"`, e `git -c chave=valor push --force`, que só perguntava em vez de negar (o `GIT_RE` agora pula as opções globais do git).
  - Falsos positivos corrigidos: `git --no-pager log` pedia aprovação; `git rm -r --cached` era lido como remoção recursiva.
  - Corpus em `hooks/corpus/gateway.jsonl`: 138 comandos, 48 tentativas de contorno, nenhuma passa. Latência do gateway igual (mediana de 151 para 153 ms no Windows).
- **A chave de assinatura fora do alcance dos agentes (S-02).** Qualquer acesso a `~/.aisef/keys` e `~/.aisef/anchors` é negado: Read, Grep, Glob, Edit, Write e comandos de shell, por caminho absoluto, `~`, `$HOME`, `$AISEF_HOME`, `$env:USERPROFILE` ou link simbólico. Antes, um `Grep` na pasta da chave lia o conteúdo sem perguntar, e `Edit` ou `echo >` reescreviam a âncora do head. A chave pública em `.aisef/keys/` do projeto continua como antes.
- **Orçamento e falta de progresso no modo contínuo (L-01 + L-06).** Novo `core/aisef_budget.py`.
  - **Orçamento por feature:** minutos desde a primeira delegação, tokens dos subagentes e despachos. Passou do limite, o `next` devolve `stop_reason: budget_exhausted`, logo depois de `critical_risk`, e não despacha mais nada da feature. Limites em `orchestration-defaults` → `budget` (480 min, 5 milhões de tokens, 30 despachos), ajustáveis no `config.json` (subir pede aprovação); o Feature Contract só pode baixar (`BUDGET-RAISED`). Não há limite em dólares: o AISEF não tem tabela de preços.
  - **Falta de progresso:** tarefa reprovada 2 vezes seguidas pelo mesmo motivo (assinatura da falha, sem números) vira `await_decision` com `source: no_progress`; só ela para, a onda segue.
  - **Agente parado:** tarefa em andamento acima de `limits.timeout_minutes` (padrão 60) vira `stale_agent`.
  - Testes em `core/test_budget.py` (22).
- **Ciclo de vida registrado pelo hook (F-04).** O hook de subagentes grava `task_started` (no SubagentStart) e `task_executed` (no SubagentStop, só com o Execution Report `executed` desta tentativa, levando os tokens), em nome do agente da tarefa. Só grava quando a ligação é exata: disparo "T-xxx:" do `dispatch`, sem dúvida de qual disparo, e papel igual ao `assigned_agent`. É idempotente. Sem relatório, o `next` passa a mostrar `await_decision` com `source: no_report`, em vez de esperar para sempre. O prompt do executor deixou de pedir `append`. Correção de quebra: um segundo start do mesmo agente consumia o disparo da próxima tentativa (`match_parents`). O registro do validador continua com o próprio validador.
- **Check com correção e `rebase-req` (F-07).** Cada achado pode trazer `fix` (`cmd` pronto ou `hint`), também no JSON; `check_project.py --fix` lista no fim os comandos, sem repetição. Regras de versão (`TASK-REQ-VERSION`, `PLAN-VERSION`, `PLAN-FEATURE-VERSION`, `RTM-TASK-NOT-LINKED`, `BP-FEATURE-VERSION`) apontam para o novo `aisef_new.py rebase-req --feature`, que leva as tarefas e o blueprint à versão atual: nova versão da tarefa cujo requisito mudou, só a base para as demais, e um `contract_changed`. Tarefa já iniciada ou blueprint que cita o requisito alterado não são reescritos: o comando pede reabertura ou nova versão do blueprint. O `next` ganha a ação `requirement_changed` e não despacha tarefa com requisito antigo. `VAL-NO-VALIDATOR`, `AGENT-PATH-CEILING`, `DESIGN-MISSING` e `STATE-*` trazem o passo de correção. Testes em `core/test_rebase.py` (28).
- **Git por risco (F-03, [ADR 0025](docs/adr/0025-git-por-risco.md)).** Numa branch de feature (`feat/*`), `git add`, `git switch`, `git checkout -b` e `git commit` não pedem mais aprovação (em dev e staging). O push da branch de feature para ela mesma é coberto por uma autorização de escopo nova, `git_feature_branch`, com `resource_filters.branches`, pedida junto com o plano. `main`, merge, release, `--force`, tags, exclusão e reescrita de histórico continuam como antes. A branch vem do `.git/HEAD`, sem subprocesso; quando não é conhecida (HEAD solto, `cd`, `git -C`), vale a regra antiga. Novo `core/aisef_git.py`; regra `AUTH-GIT-BRANCH`; contratos de agente existentes continuam valendo (quem tem `commit` pode commitar na feature; push fica com o orquestrador). Testes em `hooks/test_git_risk.py` (40).
- **Confiança em ferramentas MCP, com prazo (F-01, [ADR 0024](docs/adr/0024-confianca-mcp-com-prazo.md)).** Novo `core/aisef_mcp.py trust|revoke|list`: o usuário confia numa ferramenta ou num glob por até 7 dias, e o gateway para de perguntar; quando pergunta, a mensagem traz o comando. Ferramenta que executa código ou comandos (`execute_*`, `*_eval`, `run_*`, `sql`...) nunca entra por glob, nem no `mcp_allow`: só pelo nome exato ou com `--allow-code-execution`. Novo tipo `mcp_tool` no schema de autorização, com as regras `AUTH-SCOPE-TOO-LONG`, `AUTH-HISTORY` e `AUTH-EXPIRED` no check.
- **Sandbox nativo recomendado (F-08).** Onde o sandbox do Claude Code existe (Linux, macOS, WSL2), o `setup` ganha o item `sandbox` (`sandbox.enabled` no `.claude/settings.json`) e o doctor avisa quando ele está desligado; `"sandbox_reminder": false` no `config.json` silencia. No Windows nativo, nada muda. O gateway pergunta quando um comando pede para rodar fora do sandbox (`dangerouslyDisableSandbox`). Camadas: o sandbox isola, o gateway decide, o log prova.
- **Setup do init numa decisão só (C-03).** Novo `core/aisef_setup.py` junta o que eram quatro pedidos: ativar os agentes, as regras nativas de segunda camada, as boas práticas e a seção AISEF no `AGENTS.md` e no `CLAUDE.md` (acrescenta, nunca sobrescreve). A skill mostra o plano, o usuário desmarca o que não quer e um único `--apply` abre um prompt nativo e registra uma `decision_recorded`. Instalações de fora (Graphify, skills, plugins) continuam com o próprio prompt.
- **Gateway: instalar boas práticas é decisão do usuário.** `aisef_practices.py apply` e `aisef_project.py practices --apply` gravavam em `.claude/rules/` sem perguntar, embora a documentação dissesse que perguntavam. Agora o gateway pergunta.
- **`migrate` e `plugin_version` (F-06).** O init grava `plugin_version`; o doctor avisa quando o projeto está atrás do plugin. Novo `core/aisef_migrate.py`: migrações ordenadas e idempotentes, plano por padrão e `--apply` como decisão do usuário (o gateway pergunta), com evento `decision_recorded`. A primeira migração dá `profile: team` aos projetos antigos, preservando o comportamento.
- **Perfis de cerimônia (L-04).** `config.json` → `profile`; o init pergunta, com `solo` como padrão (`--profile`):
  - `solo`: a triagem escolhe entre rápido, enxuto e completo;
  - `team`: ciclo completo por padrão, como antes; o lean só é sugerido;
  - `regulated`: sem caminho rápido (`aisef_new quick` recusa) e novas regras `PROFILE-QUICK`, `PROFILE-TDD` (toda tarefa executora com TDD) e `PROFILE-BLUEPRINT` (risco alto exige blueprint);
  - `CONFIG-PROFILE` acusa perfil inválido. O gateway e o log assinado são iguais nos três.
- **Doctor que resolve o ambiente (C-02) e init só com log assinado (D5).**
  - novo `core/aisef_env.py`: quando falta `jsonschema` ou `cryptography`, procura outro Python que tenha as duas (PATH, sem o atalho da Microsoft Store, e `py -0p` no Windows) e diz o valor exato de `AISEF_PYTHON` para o `settings.json`; sem nenhum, mostra o `pip install` só do que falta, no Python dos hooks;
  - o doctor (SessionStart) usa esse diagnóstico;
  - **o `init` recusa sem a `cryptography`**, antes de criar qualquer arquivo, com o mesmo conselho. Projetos antigos sem assinatura continuam funcionando.

## 0.12.1: correções vindas do uso real e README novo
- **README novo** (inglês e pt-BR): a equipe de 66 agentes, as ferramentas, o radar de arquitetura e os números do benchmark na frente.
- **Gateway: leitura do log de auditoria pelo shell.** Um comando só de leitura que cita `.aisef/audit/` ou `.aisef/keys/` (por exemplo `grep ... .aisef/audit/log.jsonl | sort | uniq -c`) era negado como se fosse escrita. Agora passa, com o mesmo critério de leitura do modo Ask: nenhum redirecionamento e só comandos de leitura. Escrever (`>>`, `tee`, `sed -i`, `rm`...) continua negado. Achado no teste do deckloom.
- `aisef-init`: mostra o comando real do aisef-check (`check_project.py` com `--policy` e `--defaults`).
- **Decisão de arquitetura de nível de projeto.** `architecture_decision` aceita pedido sem `feature_id`, como na adoção do estilo de arquitetura durante a discovery, antes de existir feature. Os outros tipos de pedido continuam exigindo feature. O check e o painel tratam a ausência; no painel, o pedido aparece como "(projeto)". As skills `aisef-approve` e `aisef-discovery` explicam `feature_id` e `presented.evidence_ids` (pode ser `[]`; use o id do evento do `detect`). Bloqueava o T2 no deckloom.
- **Detecção:**
  - serviço com menos de 5 arquivos de código (por exemplo, só um `Program.cs` de health check) não sustenta "microsserviços" com confiança alta;
  - nova seção `modules`: dependências entre módulos do monólito modular. Importar a aplicação de outro módulo é permitido; importar o domínio ou a infraestrutura de outro módulo é a violação `cross-module-internal`.
  
  Achados no deckloom.
- Gateway: `git check-ignore`, `check-attr`, `ls-tree`, `rev-list`, `for-each-ref`, `cat-file`, `merge-base` e `name-rev` contam como Git só de leitura (citar `.aisef/keys/` num deles era negado), e também `git add`, `rm`, `clean` e `mv` com `-n`/`--dry-run`. Achado no deckloom.
- `aisef_practices.py` sem subcomando mostra a previa (`list`, exit 0) em vez de sair com erro de argumento (exit 2).

## 0.12.0: equipe, boas práticas e arquitetura (trilha E, port do ECC)
- **Catálogo de agentes (E0, ADR 0020).** `core/agents/catalog.v0.1.json` é a fonte única dos papéis: tipo (`executor`, `fixer`, `evaluator`, `validator`, `advisor`, `orchestrator`), ativação (`always`, `manual`, `stack:`, `arch:`, `domain:`), nível padrão na Model Policy, ferramentas e teto do Agent Contract, e prompt em `core/agents/prompts/<id>.md`.
  - `aisef_project`, `aisef_new`, `aisef_route`, `check_project` e `tools/gen_agents.py` leem do catálogo; `role_defaults` saiu da `model-policy.v0.1.json`.
  - Os enums de papel nos schemas viraram `pattern`; a nova regra **`AGENT-ROLE-UNKNOWN`** confere o papel contra o catálogo.
  - `init` e `agents` criam rascunhos só dos papéis que se aplicam ao projeto; `agents --roles x,y` cria os pedidos, inclusive os `manual`.
  - `aisef_catalog.py check|list`; testes em `core/test_catalog.py`. Os 10 agentes atuais geram os mesmos `.md`, byte a byte.
- **Equipe de agentes do ECC (E3 e E4): 56 papéis novos, 66 subagentes no total.** Texto adaptado do ECC (MIT, `THIRD_PARTY_NOTICES.md`), com blocos comuns por tipo gerados pelo `gen_agents`:
  - **avaliador**: filtro de confiança acima de 80%, prova obrigatória para CRITICAL e HIGH, zero achados é válido, lista de falsos positivos, veredito APPROVE/WARNING/BLOCK;
  - **corretor**: diff mínimo e nunca afrouxar lint, tipos ou testes para passar;
  - **consultor**: investiga e propõe, decisão é do usuário.
  - **Sempre ativos (22):** planner, architect, code-architect, code-explorer, spec-miner, code-reviewer, architecture-reviewer (novo, confere o estilo aprovado e a regra de dependência), database-reviewer, silent-failure-hunter, type-design-analyzer, pr-test-analyzer, comment-analyzer, agent-evaluator, code-simplifier, refactor-cleaner, performance-optimizer, commit-reviewer, doc-updater, docs-lookup, e2e-runner, conversation-analyzer (só propõe lições ao `aisef_learn`), harness-optimizer.
  - **Por stack detectada:** revisores Python, Django, FastAPI, TypeScript/JavaScript, Go, Rust, Java, Kotlin, Swift, C#, F#, C++, PHP, Ruby, Flutter e Godot; corretores de build TS/JS, Python, Django, Go, Rust, Java, Kotlin, Swift, Dart/Flutter, C++, PyTorch e HarmonyOS.
  - **Manuais:** RAG, ML, saúde; e os ligados a UI (React, Vue, acessibilidade, build React), que só relatam e não mexem em layout nem em tokens.
  - `security` e `database` ganharam os checklists do ECC. **`frontend`, `implementer` e `validator` não mudaram.**
- **Gateway:** subagente `aisef:<papel>` sem Agent Contract no projeto não edita nem faz operação sensível. Antes ele ficava sem teto.
- **Detecção de stack e arquitetura (E1).** `core/aisef_detect.py` (stdlib, sem modelo) e `aisef_project.py detect`.
  - **Stack:** 35 entradas em `core/detect/stacks.v0.1.json` (linguagens, frameworks, gerenciador de pacotes, comandos por stack). Derivado do ECC.
  - **Estilos com confiança e evidência:** Clean/Onion, hexagonal, DDD tático e estratégico, CQRS, event sourcing, camadas/MVC, fatias verticais, orientado a eventos, monólito modular e microsserviços. Entende nomes .NET/Java com ponto (`Loja.Pedidos.Domain`).
  - **Regra de dependência pelos imports** (Python, TS/JS, Java/Kotlin, C#, Go, PHP, Ruby, Dart, Rust): domínio importando aplicação, infraestrutura ou framework vira violação com `arquivo:linha`. `aisef_detect.py deps` sai 1 se houver.
  - **Recomendações** com motivo, impacto e esforço (corrigir a regra de dependência, definir um estilo, tirar regra de controllers, glossário DDD, avaliar DDD tático, separação CQRS, fronteiras de serviço, testes). Domínios `ml` e `rag` ativam os revisores correspondentes.
  - Grava `.aisef/architecture.json` (schema `architecture.schema.v0.1.json`) e cria os drafts dos agentes da stack. `detect --adopt <estilos> --request REQ-x` registra o estilo adotado, só com `architecture_decision` aprovado.
  - **Novas regras:** `ARCH-SCHEMA`, `ARCH-UNAPPROVED` (erro), `ARCH-PENDING` e `ARCH-DEPENDENCY` (aviso).
  - As skills `aisef-init` e `aisef-discovery` usam a detecção: confirmar o estilo no código, apresentar as recomendações e levar a adoção ao Approval Center.
  - Testes em `core/test_detect.py`, com fixtures de cada estilo.
- **Boas práticas (E2).** 33 arquivos em `core/practices/`:
  - `common/`: estilo de código, testes/TDD, revisão (severidades e veredito), segurança, Git, fluxo (search-first antes de construir), padrões, desempenho, SOLID e Clean Code;
  - `architecture/`: Clean/Onion, hexagonal, DDD tático e estratégico, CQRS/event sourcing, monólito modular, microsserviços, camadas/MVC, fatias verticais, contract-first, orientado a eventos. Cada um diz **quando não usar**;
  - `lang/`: Python, TS/JS, web, Go, Rust, Java, Kotlin, Swift, C#/F#, C++, PHP, Ruby e Dart, com `paths:` para o Claude Code carregar só nos arquivos certos.
  - `aisef_project.py practices [--apply]` (`core/aisef_practices.py`) instala em `.claude/rules/aisef/` só o que a detecção indicar; o estilo adotado prevalece; arquivo mudado no projeto é mantido sem `--force`.
  - O `pack` da tarefa traz o estilo de arquitetura e as práticas que valem para os arquivos dela. O blueprint ganhou `architecture.style` e `architecture.layers` (opcionais). O `AGENTS.aisef.md` cita o estilo adotado e as práticas.
  - Testes em `core/test_practices.py`.
- **Revisores escolhidos em código (E5).** `core/aisef_review.py`:
  - **Quem revisa:** sempre `code-reviewer`; o revisor da linguagem (pelas extensões dos caminhos da tarefa, ou pelas stacks do projeto) e o do framework (Django, FastAPI); `database-reviewer` para `data`/`db_schema`; `security` em risco alto; `architecture-reviewer` com estilo adotado ou `domain`; `pr-test-analyzer` com TDD.
  - O `aisef_new` grava `review.reviewers` em cada tarefa (o brief pode fixar ou desligar). **Risco alto: revisão dupla**, com dois `code-reviewer` independentes em níveis de modelo diferentes (ideia do santa-method do ECC).
  - O `validate-wave` devolve `reviews`, uma chamada por revisor pendente, para disparar em paralelo antes do validador. Só `APPROVE` de todos libera o validador; `WARNING`/`BLOCK` reprova e volta ao executor.
  - Reprovação no precheck ou na revisão indica o `fixer`, o corretor de build ativo da stack.
  - Tarefa antiga, sem o campo `review`, não muda de comportamento.
  - Schemas: `review` no Task Contract e no Execution Report (veredito e contagem de achados). Nova regra `REPORT-REVIEW-ROLE`.
  - A skill `aisef` traz a equipe por tipo e diz quem usar quando.
- **Gates do ECC no gateway e verify-loop (E6).**
  - **Proteção de config de qualidade** (config-protection do ECC): escrever em config de lint, formatação ou tipos (`.eslintrc*`, `eslint.config.*`, `.prettierrc*`, `biome.json`, `tsconfig*.json`, `ruff.toml`, `mypy.ini`, `.rubocop.yml`, `.golangci.yml`, `.pre-commit-config.yaml`, `.husky/` e outros) exige `config_ci_iac`. Os executores não têm esse recurso: consertam o código em vez de afrouxar a regra.
  - **`--no-verify`, `--no-gpg-sign` e `-c commit.gpgsign=false` no Git são sempre negados** (block-no-verify do ECC).
  - **`aisef_project.py verify-loop`** (`core/aisef_verify.py`): build → tipos → lint → testes por stack (de `architecture.json`, sobrescrevíveis em `config.json` → `verify`) → segredos nas linhas adicionadas do diff (o valor nunca é impresso) → resumo do diff. Ferramenta ausente vira SKIP; veredito PASS/FAIL/INCOMPLETE. `--task` grava `.aisef/evidence/VERIFY-<T>.json`. O prompt do executor manda rodar antes de entregar.
  - Testes em `core/test_verify.py` e em `hooks/test_gateway.py`.

## 0.11.0: medir
- **`aisef_project.py metrics`** (`core/aisef_metrics.py`), só leitura e sem modelo. Calcula, a partir do log (inclusive o arquivo), dos contratos e das aprovações:
  - pedidos de aprovação por tarefa e por tipo, e a fatia Git;
  - taxa de aprovação na 1ª validação e reprovações (precheck × validador);
  - despachos por tarefa;
  - lead time e espera pela validação;
  - fração do log que é `tool_used`;
  - negações e perguntas do gateway;
  - erros do check por regra.
  
  Aceita `--feature`, `--since`, `--json` e `--no-check`. Testes em `core/test_metrics.py`.
- **Benchmark de resultado (M-03).** `tools/bench_outcomes.py` com 6 tarefas em `bench/tasks/` (2 features, 2 bugs, 1 refatoração, 1 segurança), cada uma com testes escondidos e uma solução de referência.
  - `--check-fixtures` (no `run_tests.py`) garante que cada tarefa falha no repositório inicial e passa com a referência.
  - `--prepare-only` monta os dois braços sem modelo.
  - `--run` roda `claude -p` nos braços puro e AISEF (`--plugin-dir`), com o harness no papel do usuário (feature gerada e plano aprovado). Grava `docs/benchmarks/outcomes-<data>.md`.
- **Tokens e duração por subagente (M-02).** O hook `SubagentStop` soma o uso do transcript do próprio subagente (`agent_transcript_path`; o hook não traz `usage`, segundo a documentação do Claude Code).
  - Conta cada mensagem uma vez, mesmo com streaming.
  - Grava `.aisef/runtime/usage.jsonl`, um histórico local que não é truncado, com tarefa, modelo e duração.
  - O `metrics` ganha a seção "Custo": tokens faturáveis, leitura de cache à parte, por tarefa concluída e por modelo. Sem dado, mostra "não disponível", nunca zero.
- **Ligação exata subagente → tarefa.** O disparo de um agente `aisef:*` cuja descrição começa com `T-xxx:` (como o `dispatch` escreve) grava a tarefa, e o `SubagentStart` a herda.
  - O painel usa essa ligação antes da heurística por papel.
  - A lógica de "quem disparou quem" saiu do `panel_live.py` para `core/aisef_runtime.py`, compartilhada com o hook.
  - Testes em `hooks/test_agent_events.py`.
- **Graphify padrão (G-01).**
  - Projeto novo nasce com `"graphify": {"enabled": true, "backend": "none", "paths": ["docs", ".aisef"]}`: só o passo estrutural, nada enviado a provedor de modelo.
  - A `aisef-init` oferece o Graphify como primeira opção (recusar grava `enabled: false`). O codebase-memory-mcp continua opcional e em avaliação.
  - **Doctor:** lembra quando o grafo falta e avisa quando ele está velho (uma fonte mais nova que o `graph.json`, dizendo qual).
  - **Nova regra `CONFIG-GRAPHIFY`** (backend `none|ollama|auto`, caminhos relativos sem `..`).
  - Projetos antigos, sem a chave, ficam como antes.
- **O `pack` usa o grafo do Graphify (G-02).**
  - Lê o `graph.json` direto, só com a biblioteca padrão, em `core/aisef_graph.py`. O pacote do Graphify fica no Python do usuário, que o `python -I` não enxerga.
  - O pacote da tarefa ganha, com teto de 15 itens e 2.500 caracteres:
    - decisões e docs que citam os ids ou os arquivos da tarefa;
    - quem de fora depende do código dela;
    - do que ela depende.
  - Grafo velho vira aviso. `pack --no-graph` desliga, e o `dispatch` registra `context_mode` (`graphify`, `mcp` ou `none`) em cada `delegation`, para o `metrics` comparar depois (G-05).
  - Leva 10 ms num grafo de 1.262 nós.
- **Regenerar o grafo nos marcos (G-03).** O `next` traz `guide.graph_refresh` (com o comando `GRAPHIFY_BACKEND=<backend> python -m graphify update .`) quando o grafo falta ou está velho.
  - Só antes de despachar uma onda ou num marco de fase, nunca enquanto apenas espera agentes.
  - Sem hook de git.
- **Com e sem grafo, medido (G-05).** O `metrics` agrupa as tarefas pelo `context_mode` da 1ª delegação e compara, por modo: 1ª validação, despachos, lead time e tokens.
  - Com menos de 20 tarefas, avisa que a amostra é pequena para decidir.
- **Graphify neste repositório (G-04).** `graphify update .` roda sem modelo e cobre código e docs. O comando está no README de desenvolvimento, e `graphify-out/` fica fora do Git.

## 0.10.0 - 2026-11-19
- **Painel v3** (o protótipo aprovado virou o painel real; ADR 0019):
  - **Trilho de ícones com 8 telas:** Agora, Mapa dos agentes, Features e fatias, Rastreabilidade, Governança, Histórico, Engenharia e Equipe de agentes. Os links antigos continuam valendo.
  - **Mapa de execução** como visão principal da tela Agora: orquestrador, uma coluna por onda, cada fatia com estado, tempo e última ação. Os selos de aprovação e de negação do gateway ficam acima do nó, e os subagentes ficam presos a quem os disparou. Arestas: azul animada = dependência ativa; âmbar pontilhada = bloqueada por você.
  - **Estados por forma, ícone e cor** (rodando, validando, esperando outra fatia, esperando você, concluída, reprovada) e uma faixa de estados que filtra o mapa e a tabela.
  - **Raias em paralelo:** uma por fatia e por agente, com o subagente recuado. Reprovações, negações e pedidos de decisão aparecem no momento exato, e há uma linha "agora". Os ícones não cobrem mais o texto das barras, e há legenda.
  - **Gaveta da fatia** (agentes da fatia, subagentes, decisão pendente, negação, últimas ações) e **gaveta do agente** (o que pediram a ele, quem o disparou, modelo, início, tempo, número de ações e as últimas ações). Os textos longos são cortados com "…", e o texto inteiro aparece ao passar o mouse.
  - **Grafo de dependências nativo:** uma faixa por feature, arestas por estado e o caminho crítico destacado. O diagrama do fluxo da feature saiu, porque o stepper já mostra. Arquitetura e ER continuam no Mermaid, agora nas cores do tema.
  - **Busca global** (`Ctrl K` ou `/`), **atalhos** (`g` + letra, `t` para o tema, `Esc`) e filtros que sobrevivem a recarregar a página.
  - **Vidro só no que flutua** (topo, gaveta, busca, barra do celular). Claro e escuro com contraste AA nos tokens novos (3 tokens do tema claro escurecidos para passar).
  - **Correções do uso:** o hover não desloca mais os nós (piscava), os ícones não deformam no celular, nada se sobrepõe nem vaza do painel de 375 a 1440 px, e o cursor de clique aparece em tudo o que abre algo.
- **Quem disparou quem:** novo hook `PreToolUse` com matcher `Agent|Task` (`agent_events.py`, em segundo plano). Ele grava o agente que chamou, o tipo do subagente, o pedido e o modelo. O painel liga o registro ao `SubagentStart` seguinte e marca a ligação como inferida quando não há certeza.
- **Gateway:** grava o `agent_id` de quem teve a ferramenta negada, e o painel prende a negação à fatia exata.
- **Dados do painel:** `live.board` (fatias com estado visual, onda, dependências, aprovação, negação e TDD; agentes com pai, filhos, ações e modelo; raias; frase do topo).
- **Testes:**
  - autoteste da página no Chrome sem interface: nenhuma tela rola na horizontal em 375 px, e filtros, gaveta e rolagem sobrevivem à atualização ao vivo;
  - checagens novas do board e do hook de disparo;
  - contraste dos tokens v3;
  - o `run_tests.py` tolera saída que não é UTF-8.
- **README (EN e PT):** banner novo, GIFs do painel no lugar das capturas, seções "Novidades" e "O painel".

## 0.9.3 - 2026-11-18
- **Ask pesquisa na internet com precisão:**
  - o agente `aisef:ask` ganhou `WebSearch` e `WebFetch` e um método de pesquisa: fonte primária primeiro, leitura da página inteira, data e versão conferidas, duas fontes para o que decide a resposta, divergências mostradas e URLs citadas;
  - ele não se limita ao projeto quando a pergunta pede mais.
- **`/aisef:ask` escolhe o modelo pela pergunta:** Haiku para achar algo no projeto, Sonnet para pesquisa e análise (o padrão na dúvida) e Opus só a pedido.
- **Modo Ask fixo:** o lembrete por mensagem orienta a pesquisar na internet com fontes. O gateway segue liberando a pesquisa e negando URL com token.

## 0.9.2 - 2026-11-18
- **Painel redesenhado** (planejado e implementado pelo agente de frontend; plano em componentes e layouts):
  - **App shell:** barra lateral com 5 grupos e 8 telas (Agora, Features e fatias, Dependências, Rastreabilidade, Governança, Histórico, Engenharia, Equipe de agentes) no lugar das 12 abas, e barra inferior no celular. Os links antigos continuam valendo.
  - **Faixa fixa no topo:** projeto e fase, ao vivo ou estático, "Precisa de você: N", risco crítico e selo de integridade. Com a integridade comprometida, o banner fica impossível de ignorar e o comando de aprovar some.
  - **Agora:** onde estamos e o próximo passo; cartões "o que depende de você" com o comando para copiar; agentes em execução com contador e última ação; stepper de fluxo de cada feature; raia de ondas nativa (Gantt em Mermaid opcional); o que vem depois e os números do projeto.
  - **Rastreabilidade** como cadeia requisito → fatia → critério → evidência, com filtros. **Histórico** com os blocos da cadeia de hash.
  - Claro e escuro com contraste AA verificado (novo `test_panel_contrast.py`), Mermaid nas cores do tema, teclado e `prefers-reduced-motion`, de 375 a 1920 px.
  - **Atualização ao vivo por seção:** não perde rolagem, filtros, `<details>` abertos nem seleção, e os diagramas não piscam.
- **Dados:** `live.timeline[]` e `hash`/`prev_hash`/`signed` na linha do tempo (opcionais, retrocompatíveis).

## 0.9.1 - 2026-11-18
- **Modo Ask mais perto do Cursor** (explicação e comparação em `docs/guide/ask-mode.md`):
  - **`/aisef:ask`** deixou de usar `context: fork`, que entregava a pergunta a um subagente sem nenhum contexto. Agora a sessão escreve até 6 linhas do assunto em discussão e delega ao subagente `aisef:ask` (Haiku, só leitura) pela ferramenta Agent, o que é garantido para agentes de plugin. Durante essa resposta, a sessão fica sem escrita e sem shell (`disallowed-tools`).
  - **Entrar no `/aisef:modo ask` é imediato,** porque só restringe. Sair (`exec`) continua abrindo o prompt nativo.
- **README (EN e PT) reescrito** com o conteúdo da análise:
  - a mesma feature com prompt solto e com o AISEF;
  - os diagramas do gateway e do fluxo SDD + TDD;
  - a comparação com nove alternativas;
  - as sete lacunas que o AISEF cobre e os limites de cada uma;
  - onde o AISEF perde e quando não usar.

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
