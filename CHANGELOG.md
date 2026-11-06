# Changelog

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
