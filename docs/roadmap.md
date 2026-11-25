# Roadmap

O detalhe de cada versão está no [CHANGELOG](../CHANGELOG.md), e as decisões estão nos [ADRs](adr/README.md). O plano em andamento é o [plano 0.13–0.15](plan/plano-0.13-0.15.md).

`tools/gen_docs.py --check` confere que toda versão do CHANGELOG aparece aqui.

## Próximas versões

| Versão | Entrega |
|---|---|
| depois | Revisão do catálogo de agentes com dados de uso de projetos reais (C-05, `tools/agent_usage.py`) |
| depois | Confirmar numa sessão real que o Claude Code entrega o `agent_id` de quem chama a ferramenta Agent; sem isso, a ligação pai → subagente continua marcada como inferida |

## Entregues

| Versão | Entrega |
|---|---|
| 0.16.0 | Painel com informação certa e mais legível (feature aceita como aceita, mapa dos agentes por feature com linha do tempo e visão geral em cartões, alarme do gateway só quando pesa); detecção e coordenação de outra sessão no mesmo projeto |
| 0.15.5 | Repositório remoto conferido antes do primeiro push: ação `setup_remote` no `next`, aviso no doctor, init pergunta se já existe no GitHub, `remote_config` no gateway |
| 0.15.4 | Painel: com um bloco só, a coluna da direita fica com metade da altura do mapa, como no artefato aprovado |
| 0.15.3 | Painel: tempo ativo no topo, tempos decorridos que andam sozinhos, mapa de execução com altura fixa dividida em partes iguais pelos blocos da direita |
| 0.15.2 | Tabela de maturidade (uso real ou só CI), teste do ciclo inteiro nas 48 combinações de modos, números do README conferidos contra o código |
| 0.15.1 | Painel: custo de atenção na tela Agora (F-09), filtro "impacto de" na Rastreabilidade (G-07), tela Agora sem o bloco "Próximo passo" |
| 0.15.0 | Times e auditores: Action `aisef-verify` em cada PR, pacote de evidência por feature (SOC 2 CC8.1, ISO 27001 A.8.32 e A.5.3), exportação OpenTelemetry, um log por pessoa, README pela trilha de evidência e roadmap conferido |
| 0.14.0 | Módulos com até 500 linhas, grafo do sistema consultável (`aisef_sysgraph`), workflow declarativo (`workflow.v0.1.json`), log em camadas com telemetria, custo de atenção no `metrics`, worktree por fatia |
| 0.13.0 | Triagem em código e caminho enxuto, perfis solo, team e regulated, catálogo em núcleo e estendido, gateway por tokens com corpus de contornos, Git por risco, MCP com prazo, orçamento e falta de progresso no loop, ciclo de vida pelo hook, `check --fix`, grafo nativo de imports |
| 0.12.1 | Correções vindas do uso real (decisão de arquitetura do projeto, fronteira entre módulos, Git só de leitura) e README novo |
| 0.12.0 | Trilha E ([plano](plan/trilha-e-ecc.md)): 66 agentes num catálogo, detecção de stack e arquitetura, boas práticas, revisores em código, `verify-loop` |
| 0.11.0 | Medir: `metrics`, benchmark de resultado, tokens por subagente, Graphify padrão |
| 0.10.0 | Painel v3: mapa de execução, raias em paralelo, quem disparou quem, gaveta do agente, grafo de dependências com caminho crítico |
| 0.9.3 | O modo Ask pesquisa na internet com fontes e escolhe o modelo pela pergunta |
| 0.9.2 | Painel redesenhado (componentes e layouts) |
| 0.9.1 | Modo Ask mais perto do Cursor |
| 0.9.0 | Modo Ask: `/aisef:ask` só de leitura e `/aisef:modo ask` aplicado pelo gateway |
| 0.8.2 | Busca de ferramentas por gatilho, revisão periódica (`/skill-doctor`, `claude plugin eval`), desinstalação com aprovação |
| 0.8.1 | Aprendizado contínuo revisado e estado que sobrevive ao `/compact` |
| 0.8.0 | Painel ao vivo (servidor local), aba Agora, fluxo da feature, ondas em Gantt, estado efetivo |
| 0.7.0 | `dispatch` da onda numa chamada, validação por onda, `precheck` determinístico, auditoria assíncrona das edições |
| 0.6.1 | Autoridade de design por projeto, `design_check` e frontend dentro dos tokens |
| 0.6.0 | SDD + TDD com fatias verticais, `implementer`, evidência de TDD checada e guia de fases |
| 0.5.3 | Documentação reorganizada |
| 0.5.2 | O gateway e a auditoria passam a cobrir a ferramenta PowerShell |
| 0.5.1 | `check_project` aceita a raiz do repositório |
| 0.5.0 | Modo contínuo (`next`) e branch por feature |
| 0.4.0 | Modelo e effort por tarefa (`aisef_route`) e memória de projeto |
| 0.3.0 | Sugestão de ferramentas (`aisef-tooling`) |
| 0.2.0 | MCP e WebFetch no gateway, registro das tentativas bloqueadas |
| 0.1.0 | Primeira versão como plugin do Claude Code |

## Itens antigos de `pending.md`

| Item | Destino |
|---|---|
| Registrar no log as tentativas que o gateway bloqueou | Concluído na 0.2.0 |
| Ícone do plugin | Concluído |
| Rotação de chaves do Audit Signer | Concluído (`aisef_project.py rotate-key`) |
| Ancoragem externa do head | **Descartado:** a âncora local fora do repositório (`~/.aisef/anchors/`) cobre o uso individual, e uma âncora remota exigiria aprovação de push a cada checkpoint ([ADR 0005](adr/0005-log-de-auditoria-assinado-com-head-externo.md)) |
