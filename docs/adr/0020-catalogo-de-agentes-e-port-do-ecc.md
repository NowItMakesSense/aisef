# ADR 0020: Catálogo de agentes e port da equipe do ECC

- **Status:** aceito
- **Data:** 2026-11-19

## Contexto

O usuário pediu uma equipe de agentes grande e detalhada, trazendo "tudo que o ECC tem" (affaan-m/everything-claude-code, licença MIT, 72 agentes). Também pediu boas práticas e detecção de arquitetura. Pediu ainda para **quebrar o congelamento** do plano `docs/plan/melhorias-0.11-0.14.md`: o que depender de avaliação vai para uma lista, tratada depois. O agente `frontend` fica como está, porque gera bons layouts hoje.

Até a 0.11, os papéis de agente estavam fixos em sete lugares:
- os perfis do Agent Contract;
- os enums de três schemas;
- os padrões da Model Policy;
- `AGENT_ROLES` do `aisef_new`;
- os papéis avaliadores do check;
- o gerador de agentes.

Com mais de 60 papéis, isso não escala.

## Decisão

- **Fonte única:** `core/agents/catalog.v0.1.json` (schema `agent-catalog.schema.v0.1.json`), com um prompt por papel em `core/agents/prompts/<id>.md`. `core/aisef_catalog.py` expõe:
  - os perfis do Agent Contract;
  - os ids;
  - os níveis da Model Policy;
  - os avaliadores;
  - os papéis validáveis;
  - a ativação.
- **Tipos (`kind`):**
  - `executor`, `fixer` (diff mínimo) e `advisor` (não edita código de produção);
  - `evaluator` e `validator` (só relatam; o catálogo recusa Edit/Write neles);
  - `orchestrator`.
- **Ativação:** cada papel tem uma de `always`, `manual`, `stack:<id>`, `arch:<id>` ou `domain:<id>`.
  - `init` e `agents` só criam rascunhos dos papéis que se aplicam ao projeto (`.aisef/architecture.json`).
  - Papéis `manual` só entram a pedido do usuário. Ativar continua sendo decisão dele.
- **Schemas:** os enums de papel viram `pattern`. A nova regra `AGENT-ROLE-UNKNOWN` confere o papel contra o catálogo.
- **Model Policy:** `role_defaults` sai do arquivo e vem do campo `level` do catálogo. Um `role_defaults` escrito na política ainda prevalece.
- **Port do ECC:** os agentes de engenharia vêm do ECC, com texto adaptado (pt-BR, Agent Contract, gateway) e atribuição MIT em `THIRD_PARTY_NOTICES.md`. Ficam de fora:
  - agentes sem relação com a engenharia do projeto (chief-of-staff, marketing, seo, homelab/network, bengali, opensource-*);
  - o GAN harness, que mexe na UI viva;
  - `loop-operator` e `tdd-guide`, já cobertos pelo modo contínuo e pelo `implementer`.
- **Frontend:** o agente `frontend`, a skill `aisef-design` e `design_check.py` não mudam. Os agentes do ECC ligados a UI (react/vue reviewer, a11y-architect, react-build-resolver) entram com ativação `manual` e só relatam.

## Consequências

- Adicionar um papel passa a ser uma entrada no catálogo mais um prompt. `gen_agents --check` e `aisef_catalog check` mantêm tudo em sincronia.
- Os 10 agentes atuais geram os mesmos `.md`, byte a byte.
- **Custo:** cada agente do plugin entra na descrição da ferramenta Agent em toda sessão. Fica na lista de avaliação: medir os tokens e, se pesar, separar pacotes por stack.
