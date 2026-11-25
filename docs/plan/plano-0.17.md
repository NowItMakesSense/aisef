# Plano 0.17: fechar o que o README promete

> **Status:** em andamento, desde 2026-11-25.
> **Origem:** análise de 2026-11-25 (nota geral 6,9). Notas por área e provas estão na seção 5.
> **Como retomar (sessão nova ou depois do `/compact`):** leia só a seção 1 (Estado). Pegue a primeira tarefa `[ ]`
> e leia o bloco dela na seção 3. Não releia a análise nem o código inteiro.

## 1. Estado

Legenda: `[x]` feito, `[~]` em andamento, `[ ]` a fazer, `[u]` depende do usuário (custa dinheiro ou é uso real).

| Ordem | ID | Tarefa | Estado | Nota da área: antes → meta |
|---|---|---|---|---|
| 1 | S-03 | Gateway: fechar os 7 contornos provados | `[x]` | Gateway 6,0 → 7,5 |
| 2 | H-05 | Higiene do CI: `permissions`, Actions por SHA, dependências com hash | `[x]` | Engenharia 8,0 → 8,5 |
| 3 | D-03 | README e maturidade sem promessa maior que o código | `[x]` | Tese 8,5 (mantém) |
| 4 | E-01 | TDD cruzado com o log assinado (`TDD-EVIDENCE-UNBACKED`) | `[x]` | SDD/TDD 7,0 → 8,5 |
| 5 | S-04 | Sandbox estrito nos perfis `team` e `regulated` | `[x]` | Gateway → 8,0 |
| 6 | S-05 | Dependência nova pergunta e é conferida (registro, idade, OSV) | `[x]` | Segurança |
| 7 | S-06 | Conteúdo não confiável marca a sessão e endurece a saída de dados | `[x]` | Segurança |
| 8 | E-04 | Validação às cegas | `[ ]` | Validador 7,0 → 8,0 |
| 9 | E-03 | Carimbo de tempo RFC 3161 nos marcos | `[ ]` | Log 6,5 → 8,0 |
| 10 | E-02 | Chave privada no cofre do sistema | `[ ]` | Log → 8,5 |
| 11 | E-05 | Atestado in-toto e mapeamento ISO 42001, EU AI Act art. 12, NIST AI RMF | `[ ]` | Evidência 5,5 → 7,5 |
| 12 | M-07 | Avaliação por revisor com bugs plantados | `[ ]` | Equipe 6,0 → 7,5 |
| 13 | M-06 | Benchmark nas 6 tarefas, com o braço enxuto | `[u]` | Prova de valor 3,5 → 6,0 |
| 14 | M-05 | Linha de base num projeto real (herdada do plano 0.13–0.15) | `[u]` | Prova de valor |

**Versão:** a 0.16.0 saiu no PR #39. As entregas deste plano entram na seção `## 0.17.0 (em andamento)` do
CHANGELOG; o bump do `plugin.json` e do marketplace é feito no fechamento.

**PRs:** S-03 a S-05 entraram na `main` pelo PR #43. S-06 no PR #44 (branch `feat/v0.17-s06`). Próximas
tarefas: commits na mesma branch até o merge; depois, branch nova a partir da `main`. Cuidado: outra sessão no mesmo
repositório pode trocar a branch da pasta; confira `git status -sb` antes de commitar.

**Fechamento de cada tarefa:** teste próprio no `run_tests.py`, CHANGELOG, linha na tabela de maturidade
(`docs/reference/maturity.md`, exigida pelo `tools/gen_docs.py --check` para todo ID citado no CHANGELOG), ADR
quando muda a política, e o estado nesta seção.

## 2. Decisões que valem para todas as tarefas

- Cada afrouxamento ou endurecimento de política tem teste de negação no corpus (`hooks/corpus/gateway.jsonl`).
- O que o gateway não consegue ler vira `ask`, nunca `allow`. `deny` só quando há certeza (chave do AISEF).
- Só biblioteca padrão mais `cryptography` e `jsonschema`. Nada de dependência nova no plugin.
- Windows nativo não tem o sandbox do Claude Code: tudo que depende dele precisa de alternativa (WSL2 ou devcontainer)
  e de aviso claro no doctor.

## 3. Tarefas

### S-03: Gateway, fechar os 7 contornos provados

Prova (2026-11-25, `gateway.py` num projeto temporário): todos estes deram `allow`.

| # | Comando | Deve dar | Como |
|---|---|---|---|
| 1 | `cat ~/.ais''ef/keys/x` | deny | Normalizar o comando tirando aspas vazias e aspas no meio de palavras antes do `home_secret_ref` |
| 2 | `d=.aisef; cat ~/$d/keys/x` | ask | Variável ou subshell num caminho da home junto de `keys`/`anchors` vira `ask` (não dá para ler) |
| 3 | `cp -r ~/.ais* /tmp/k` | ask | Curinga na home: expandir com `fnmatch` contra `.aisef` (o `glob` real pode não existir) |
| 4 | Write `x.py` que lê a chave, depois `python x.py` | ask no Write | Conteúdo escrito (Write/Edit `content`/`new_string`) citando `.aisef/keys` ou `.aisef/anchors` da home |
| 5 | `npm run deploy`, `make release` | deploy (negado sem reforçada); `make release` ask | `(npm\|pnpm\|yarn\|bun) run <alvo>` e `make\|just\|task <alvo>` com alvo `deploy\|release\|publish\|ship\|prod*` |
| 6 | `curl -X POST … -d @.env` | ask; deny se arquivo sensível | Sem recurso novo (evita mexer em 5 schemas): `unclassified`; `curl -d/--data*/-F/-T @arquivo`, `wget --post-file`, `Invoke-WebRequest -InFile`, `scp`/`rsync` para host remoto |
| 7 | Edit em `.git/hooks/pre-commit` | ask | `.git/hooks/`, `.githooks/`, a pasta `hooks/` do plugin e `core.hooksPath` entram no `CONFIG_PATH_RE` |

- **Feito (2026-11-25):** `hooks/gateway_rules.py` (`_variants`, `home_secret_hint`, `code_secret_ref`,
  `SCRIPT_DEPLOY_RE`, `EGRESS_RE`, `SHELL_HOOK_WRITE_RE`), chamadas em `hooks/gateway.py`, corpus 168 casos / 65
  contornos, 7 casos de Write/Edit em `test_gateway_corpus.py`. `python x.py` depois do Write continua livre: só o
  sandbox (S-04) fecha isso.
- **Aceite:** os 7 casos no corpus com `"bypass": true`; nenhum caso legítimo do corpus muda; `check_policy_consistency`
  aceita o recurso novo; o teto dos agentes (`agent-contract`) trata `network_egress` como os demais.
- **Teste rápido:** `python -I plugins/aisef/hooks/test_gateway_corpus.py` e `python -I plugins/aisef/hooks/test_gateway.py`.

### H-05: Higiene do CI

- `permissions: contents: read` no topo do `.github/workflows/ci.yml` e na Action, quando cabível.
- Actions fixadas pelo SHA do commit, com a tag em comentário (`actions/checkout@<sha> # v4`).
- `requirements-dev.txt` com versões exatas e `--require-hashes` (gerar com `pip-compile --generate-hashes` ou à mão
  com `pip hash`). Manter `>=` só no que o plugin pede ao usuário (o doctor).
- `run_tests.py --jobs N`: suítes independentes em paralelo (hoje mais de 10 minutos no Windows local).
- **Aceite:** CI verde; tempo local cai pela metade com `--jobs 4`.
- **Feito (2026-11-25):** `requirements-dev.lock` (uv, universal, com hash), SHAs no `ci.yml` e na Action, entradas da
  Action por `env`, `run_tests.py --jobs/--only` (5 min com `--jobs 6`). Falta só ver o CI verde no GitHub.

### D-03: README e maturidade honestos

- Trocar "48 of them bypass attempts, none get through" por "N contornos conhecidos bloqueados; o isolamento de verdade
  é o sandbox" (nos três READMEs; o `gen_docs --check` confere os números).
- Seção curta "O que o gateway não garante": é um hook no mesmo usuário do sistema; script escrito e depois executado
  só é pego pelo sandbox.
- **Aceite:** `gen_docs --check` verde; números batem com o corpus.

### E-01: TDD cruzado com o log assinado

- **Problema:** `check_rules_2.py:227-241` confere `exit_code` e horário que o próprio agente declarou.
- **Spike (feito):** o `PostToolUse` só dispara com sucesso e não traz código de saída (`stdout`, `stderr`,
  `interrupted`, `isImage`). A falha vai para o `PostToolUseFailure`, com `error` cuja primeira linha é `Exit code N`
  (doc oficial dos hooks). O AISEF não ouvia esse evento: o vermelho nunca chegava ao log.
- **Feito (2026-11-25), branch `feat/v0.17-e01` (em cima do PR #40):** hook grava `exit_code`; `PostToolUseFailure`
  no `hooks.json`; regra em `core/check_rules_4.py` casando por comando, resultado e janela de 15 min, sem `event_id`
  (o agente não precisa saber o id); erro em `team`/`regulated`, aviso em `solo`; só cobra ciclos com o verde depois
  do primeiro comando gravado com resultado. Suíte `core/test_tdd_log.py`.
- **Mudança:** o `audit_hook.py` grava `exit_code` (ou `failed: true`) no `tool_used` do Bash. Cada ciclo do
  `tdd_evidence` ganha `red.event_id` e `green.event_id`. Regra nova `TDD-EVIDENCE-UNBACKED`: o evento existe no log,
  é um comando de teste, tem o mesmo resultado (falhou / passou) e a ordem bate. Perfil `solo`: aviso. `team` e
  `regulated`: erro.
- **Arquivos:** `hooks/audit_hook.py`, `core/execution-report.schema.v0.1.json`, `core/check_rules_2.py`, prompts do
  `implementer` e dos executores (`core/agents/prompts/`), `tools/gen_agents.py`.
- **Aceite:** teste de mutação no `test_check_project.py` (ciclo com `event_id` inexistente, com resultado trocado e
  com ordem trocada); o ciclo inteiro do `test_modes.py` passa.

### S-04: Sandbox estrito nos perfis `team` e `regulated`

- O setup grava em `.claude/settings.json`: `sandbox.enabled: true`, sem saída por `dangerouslyDisableSandbox`
  (conferir o nome exato da opção na doc oficial antes), `denyRead` em `~/.aisef`, lista de domínios de rede.
- Doctor: perfil `team`/`regulated` sem sandbox vira aviso forte; no Windows nativo, recomenda WSL2 ou devcontainer.
- Regra `PROFILE-SANDBOX` no check (aviso, porque depende da máquina).
- Template de devcontainer opcional em `core/templates/`.
- **Aceite:** `test_modes.py` cobre os três perfis; o doctor no Windows não acusa erro, só recomenda.
- **Feito (2026-11-25), branch `feat/v0.17-s04`:** `aisef_env.py` (`SANDBOX_STRICT`, `sandbox_effective`,
  `sandbox_missing`, `sandbox_merge`, aviso por perfil), setup grava em qualquer sistema, regra `PROFILE-SANDBOX` em
  `check_rules_4.py`, testes em `test_env.py` e `test_setup.py`. `failIfUnavailable` não é gravado (travaria o Claude
  Code no Windows nativo). **Ficou para depois:** template de devcontainer em `core/templates/` e `permissions.deny`
  com `Read(~/.aisef)` (a doc não confirma que `~` expande ali; o gateway já nega a leitura pelo Read).

### S-05: Dependência nova

- Classificar `pip install X`, `uv add`, `poetry add`, `npm install X`/`i X`/`add`, `pnpm add`, `yarn add`, `cargo add`,
  `go get`, `dotnet add package`, `gem install`, `composer require`. Instalar o que já está no lockfile
  (`npm ci`, `pip install -r`, `uv sync`) continua livre.
- `core/aisef_deps.py check <ecossistema> <pacote>`: existe no registro, idade do pacote, vulnerabilidades no OSV
  (`api.osv.dev`). Só rede quando o usuário pede; o resultado entra no motivo do `ask`.
- **Aceite:** corpus com 10 casos; pacote inexistente aparece como "não existe no registro (possível pacote inventado)".

### S-06: Conteúdo não confiável

- `PostToolUse` de WebFetch, WebSearch e MCP fora do `mcp_allow` marca a sessão em `.aisef/runtime/` (com prazo).
- Com a marca, saída de dados (`network_egress`) e escrita em config/CI sobem um nível. Regra da "lethal trifecta":
  dado privado + conteúdo não confiável + canal de saída.
- **Aceite:** teste com a sequência WebFetch → `curl -d @arquivo`; a marca expira.

### E-04: Validação às cegas

- O brief do validador (`aisef_dispatch.py`, `aisef_review.py`) leva o Task Contract, o diff e os testes, e não leva o
  resumo de sucesso do executor nem os achados dos revisores. Base: framing "está correto" reduz a detecção em 16–93%
  (arXiv 2603.18740).
- **Aceite:** teste do brief: nenhum campo `summary`/`result` do Execution Report do executor aparece.

### E-03: Carimbo RFC 3161 nos marcos

- `core/aisef_anchor.py stamp`: monta o `TimeStampReq` em DER à mão (SHA-256 da cabeça do log, nonce, `certReq`),
  envia por HTTP à TSA configurada (`audit.tsa_url`, padrão freetsa.org) e guarda o token em
  `.aisef/audit/timestamps/`. Roda no aceite de feature e no `aisef-verify` da PR, nunca a cada evento.
- Verificação: `openssl ts -verify` quando houver; sem ele, confere o hash e o nonce e avisa que a cadeia da TSA não
  foi conferida.
- Alternativa registrada: Sigstore Rekor (mais pesado; fica para depois).
- **Aceite:** teste com TSA falsa local; aceite de feature sem rede segue, com aviso.

### E-02: Chave no cofre do sistema

- Opção `audit.key_store`: `file` (hoje), `os` (DPAPI no Windows por `ctypes`, Keychain no macOS por `security`,
  Secret Service no Linux por `secret-tool`). Migração pelo `migrate`.
- **Aceite:** ida e volta da chave nos três sistemas no CI (Linux e Windows; macOS só se houver runner).

### E-05: Atestado e conformidade

- `aisef_evidence.py build --in-toto`: um Statement v1 por tarefa (subject: arquivos e commit; predicate: contrato,
  modelo, ferramentas, testes, validação), assinado com a chave do projeto em envelope DSSE.
- Tabela de controles ganha ISO/IEC 42001 (Anexo A), EU AI Act art. 12 (registro de eventos) e NIST AI RMF (Govern,
  Map, Measure, Manage).
- **Aceite:** o pacote verifica sozinho; o DSSE confere com a chave pública.

### M-07: Avaliação por revisor

- `bench/reviewers/`: 10 a 20 diffs com bug plantado, um por categoria (segurança, SQL, tipos, falha silenciosa,
  teste fraco) e diffs limpos. `tools/bench_reviewers.py` mede precisão e recall por agente.
- Alimenta a C-05 (cortar agentes que não se pagam).

### M-06 e M-05 (usuário)

- M-06: `python tools/bench_outcomes.py --run --reps 3` nas 6 tarefas, braços `plain`, `aisef`, `aisef-lean`
  (custo estimado de US$ 30 a 50). Medir defeito que escapa, não só teste passando.
- M-05: uma feature real com a versão atual, depois `aisef_project.py metrics`.

## 4. Riscos

| Risco | Mitigação |
|---|---|
| S-03 pergunta demais em comandos legítimos | Corpus com casos legítimos; meta de zero regressões |
| E-01: o hook não traz o código de saída | Spike primeiro; alternativa é o agente rodar o teste pelo `verify-loop`, que grava o resultado |
| S-04 não existe no Windows nativo | Doctor recomenda WSL2 ou devcontainer; o gateway continua como camada |
| E-03 depende de rede | Carimbo só nos marcos; sem rede vira aviso e fica pendente para o próximo marco |

## 5. Notas da análise de 2026-11-25

Tese 8,5 · Rastreabilidade 8,5 · Documentação 8,5 · Engenharia 8,0 · Painel 8,0 · Radar 7,5 · SDD/TDD 7,0 ·
Validador 7,0 · Triagem 7,0 · Loop 7,0 · Aprendizado 7,0 · Action 7,0 · OTel 7,0 · Log 6,5 · Equipe 6,0 ·
Gateway 6,0 · Evidência 5,5 · Atenção 5,5 · Prova de valor 3,5. Geral 6,9.

Fontes principais: OWASP Top 10 for Agentic Applications 2026 (ASI01, ASI02, ASI04); doc oficial do Claude Code
(permissões, hooks, sandbox); transparency.dev; OTel GenAI agent spans (status Development); NIST AI RMF ↔ ISO 42001
crosswalk; arXiv 2603.18740 (viés de confirmação na revisão).
