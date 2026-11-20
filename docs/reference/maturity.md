# Maturidade dos recursos

O que já rodou num projeto de verdade e o que, por enquanto, só tem teste automatizado. Use esta tabela para decidir
o que ligar num projeto sério e como voltar atrás se algo atrapalhar.

O `tools/gen_docs.py --check` (roda no `run_tests.py`) falha quando o CHANGELOG cita, da 0.13 em diante, um ID de
tarefa que não está aqui.

## Níveis

| Nível | O que quer dizer |
|---|---|
| **Uso real** | Rodou num projeto de verdade, e o que apareceu foi corrigido |
| **CI** | Tem suíte própria e entra no teste de combinações (`core/test_modes.py`: perfil × caminho × paralelismo × telemetria × streams, ciclo inteiro), mas ainda não rodou num projeto real |
| **CI, opcional** | Como CI, mas fica desligado até você ligar |

Até a 0.12.1, tudo passou por uso real (deckloom). Os recursos da 0.13 à 0.15 vão passar pelo teste de uso real no
próximo projeto. Até lá, eles ficam como **CI**.

## Da 0.13 em diante

| ID | Recurso | Versão | Nível | Padrão | Como voltar atrás |
|---|---|---|---|---|---|
| C-01 | Triagem em código e caminho enxuto | 0.13.0 | CI | ligado | `aisef_triage.py --force full` numa feature, ou `profile: "team"` (lean vira sugestão) |
| C-02 | Doctor acha o Python com as bibliotecas; init só com log assinado | 0.13.0 | CI | ligado | `AISEF_PYTHON` aponta o Python na mão |
| C-03 | Setup do init numa decisão só | 0.13.0 | CI | ligado | Recuse o lote e aplique item a item (`agents`, `practices --apply`) |
| C-04 | Catálogo em núcleo e estendido | 0.13.0 | CI | ligado | `aisef_project.py agents --roles <papel>` ativa qualquer estendido |
| D5 | Init recusa sem `cryptography` | 0.13.0 | CI | ligado | Sem volta, por decisão: instale `cryptography` |
| F-01 | Confiança em ferramenta MCP com prazo | 0.13.0 | CI, opcional | desligado | `aisef_mcp.py revoke` |
| F-02 | Corpus de testes do gateway | 0.13.0 | CI | ligado | Não muda comportamento (só teste) |
| F-03 | Git por risco: commit livre em `feat/*`, push pelo escopo | 0.13.0 | CI | ligado | Commit e push fora de `feat/*` continuam pedindo; revogue o escopo da feature |
| F-04 | Hook registra `task_started` e `task_executed` | 0.13.0 | CI | ligado | O orquestrador também pode registrar; o hook é idempotente |
| F-06 | `migrate` e `plugin_version` | 0.13.0 | CI | sob pedido | Só roda quando você manda |
| F-07 | Check com correção sugerida e `rebase-req` | 0.13.0 | CI | ligado | `--fix` só lista comandos; nada roda sozinho |
| F-08 | Sandbox nativo no setup e no doctor | 0.13.0 | CI, opcional | sugerido | `sandbox.enabled: false` no `.claude/settings.json` |
| G-06 | Grafo nativo de imports sem o Graphify | 0.13.0 | CI | ligado sem Graphify | Instale o Graphify: ele tem prioridade |
| L-01 | Orçamento por feature no modo contínuo | 0.13.0 | CI | ligado | `budget` no `config.json` (sobe os limites do projeto) |
| L-04 | Perfis solo, team e regulated | 0.13.0 | CI | `solo` | `profile` no `config.json` |
| L-06 | Parar quando a mesma falha se repete | 0.13.0 | CI | ligado | `budget.no_progress_repeats` no `config.json` |
| S-01 | Gateway lê comandos por partes | 0.13.0 | CI | ligado | Sem volta: é a camada de segurança |
| S-02 | Chave de assinatura fora do alcance dos agentes | 0.13.0 | CI | ligado | Sem volta: é a camada de segurança |
| F-05 | Log em camadas (edições e MCP na telemetria) | 0.14.0 | CI | `split` em projeto novo | `audit.telemetry: "signed"` põe tudo no log assinado |
| F-09 | Custo de atenção (métrica e card do painel) | 0.14.0 | CI | ligado | Só leitura |
| G-07 | Grafo do sistema (`impact`, `why`) e filtro no painel | 0.14.0 | CI | ligado | Só leitura |
| H-01 | Módulos menores, sem mudar comportamento | 0.14.0 | CI | — | Refatoração; a API de `aisef_project` ficou igual |
| L-02 | Worktree por fatia | 0.14.0 | CI, opcional | desligado | `parallel.mode: "paths"` (o padrão) |
| L-02a | Hooks dentro de um worktree gravam no `.aisef` principal | 0.14.0 | CI | ligado | Só age dentro de worktree |
| L-03 | Workflow declarativo (`workflow.v0.1.json`) | 0.14.0 | CI | ligado | — (é a fonte do fluxo) |
| D-02 | README pela trilha de evidência | 0.15.0 | — | — | Documentação |
| H-02 | Roadmap conferido contra o CHANGELOG | 0.15.0 | CI | — | Documentação |
| T-01 | GitHub Action `aisef-verify` | 0.15.0 | CI, opcional | desligado | Não inclua a Action no workflow |
| T-02 | Pacote de evidência por feature | 0.15.0 | CI | sob pedido | Só roda quando você manda |
| T-03 | Exportação OpenTelemetry | 0.15.0 | CI | sob pedido | Só roda quando você manda |
| T-04 | Log por pessoa (streams) | 0.15.0 | CI, opcional | desligado | Não há como desligar depois de ligado; ligue só quando houver mais de uma pessoa |
| T-05 | Decisão assinada por quem decidiu; CI pega o corte de um stream | 0.15.0 | CI, opcional | com streams | Vem com o T-04 |
| H-03 | Números do README conferidos contra o código | 0.15.2 | CI | — | Documentação |
| H-04 | Teste de combinações de modos | 0.15.2 | CI | — | Só teste |
