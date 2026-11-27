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
| F-10 | Dependências entre features exigidas no brief e conferidas no check (`FEATURE-DEPS-UNDECLARED`, `FEATURE-DEP-UNKNOWN`, `FEATURE-DEP-CYCLE`) | não lançado | CI e HireMe | ligado | Contrato antigo sem o campo só gera aviso |
| U-01 | Painel em telas pequenas e baixas: todas as telas na barra do celular, busca no celular, reflow a 320 px, alvos de 24 px, teclado nos cartões | não lançado | CI (estático) e auditoria manual no navegador | ligado | Pontos sobrepostos em Entregas no tempo continuam sobrepostos; a gaveta da feature é o caminho alternativo |
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
| S-03 | Gateway: sete contornos fechados (aspas, variável e curinga na home, script que lê a chave, deploy por script, saída de dados, hook do Git) | 0.17.0 | CI | ligado | Sem volta: é a camada de segurança |
| D-03 | README sem promessa maior que o código | 0.17.0 | — | — | Documentação |
| H-05 | CI só leitura, Actions por SHA, dependências com hash, suíte em paralelo | 0.17.0 | CI | ligado | `run_tests.py` sem `--jobs` roda em série, como antes |
| E-01 | Evidência de TDD conferida no log assinado (`PostToolUseFailure`, `TDD-EVIDENCE-UNBACKED`) | 0.17.0 | CI | ligado | Perfil `solo` deixa a regra só como aviso |
| S-04 | Sandbox estrito nos perfis `team` e `regulated` (setup, doctor, `PROFILE-SANDBOX`) | 0.17.0 | CI | sob pedido (setup) | Recuse o item `sandbox` do setup; `profile: "solo"` volta ao aviso simples |
| S-05 | Dependência nova pergunta; `aisef_deps.py check` confere registro, idade e OSV | 0.17.0 | CI | ligado (rede só com `dependency_check: "online"`) | Sem volta para o ask; tire `dependency_check` para voltar ao modo sem rede |
| S-06 | Conteúdo não confiável marca a sessão; saída de dados, config/CI e rede ficam mais restritas até a marca vencer | 0.17.0 | CI | ligado | `untrusted_ttl_minutes: 1` no config.json quase desliga |
| S-07 | Gateway pergunta em código inline citando `.aisef`, cópia da home inteira e pacote baixado na hora; nega caminho da chave montado por concatenação | 0.17.0 | CI (corpus) | ligado | Código montado de jeitos que o gateway não lê ainda passa; o isolamento é o sandbox |
| E-02 | Chave privada do log no cofre do sistema (DPAPI, Keychain, Secret Service), com migração ida e volta | 0.17.0 | CI (cofre real em Linux, macOS e Windows) | desligado (`audit.key_store: os` liga) | Não protege contra código na mesma sessão do usuário; o apagamento do PEM não é físico |
| E-05 | Atestado in-toto (DSSE) por tarefa e controles ISO/IEC 42001, EU AI Act art. 12 e NIST AI RMF no pacote de evidência | 0.17.0 | CI | sob pedido (`--in-toto`) | Mapeamento indicativo; o digest dos arquivos é o do momento em que o pacote é montado |
| M-06 | Benchmark de resultado com o braço enxuto (`aisef-lean`, triagem real no perfil solo) | 0.17.0 | CI (preparo, sem modelo) | sob pedido (`--run`) | A rodada paga nas 6 tarefas ainda não foi feita |
| M-07 | Revisores avaliados com 20 diffs de bug plantado (precisão, recall, falso alarme por agente) | 0.17.0 | CI (fixtures e placar) | sob pedido (`--run`) | A rodada com modelo ainda não foi feita; sem ela não há números |
| E-03 | Carimbo de tempo RFC 3161 nos marcos do log (aceite de feature e `aisef-verify --stamp`), conferido contra o log | 0.17.0 | CI (TSA falsa) | desligado (`audit.tsa_url` liga) | Sem `openssl` e `audit.tsa_ca_file`, a cadeia da TSA não é conferida |
| E-04 | Validação às cegas: o brief do validador leva só fatos, sem o resumo do executor nem os achados dos revisores | 0.17.0 | CI | ligado | Sem volta: é a independência do validador |
