# ADR 0023: Triagem em código e caminho enxuto

- **Status:** aceito
- **Data:** 2026-11-20
- **Complementa:** [ADR 0009](0009-briefs-e-caminho-rapido.md)

## Contexto

Até a 0.12, toda mudança ia pelo ciclo completo (Grill, Spec, fatias, blueprint, vários revisores e validador), a não ser que o modelo escolhesse o caminho rápido. A escolha era do modelo, e não havia nada no meio. Numa tarefa pequena, o benchmark mediu cerca de 11 vezes o custo do Claude Code puro, com o mesmo resultado nos testes escondidos.

## Decisão

- **A triagem é código** (`core/aisef_triage.py`). O orquestrador estrutura o pedido (caminhos, tipos de mudança, arquivos, linhas, fatias, risco) e o script devolve `quick`, `lean` ou `full`, com os motivos.
- **Sinais que forçam `full`:**
  - caminho que exige recurso além de `repo_code`, pela mesma classificação de escrita do gateway;
  - migração ou schema de banco, autenticação, autorização ou criptografia;
  - tipos de mudança `api`, `schema`, `security`, `ci`, `infra`, `dependency_breaking`, `public_contract` e `cross_module`;
  - risco `high` ou `critical`;
  - mais de uma fatia, mais de 5 arquivos ou tamanho desconhecido.
- **`lean`** é o caminho novo: Feature Contract curto, uma fatia com TDD, sem blueprint, só o `code-reviewer`, validador independente e RTM completa.
- **O perfil pesa** (`config.json` → `profile`):
  - `solo` usa a triagem;
  - `team`, o padrão de projetos sem perfil, mantém o comportamento anterior e só sugere o `lean`;
  - `regulated` desliga o caminho rápido.
- **Só se sobe de caminho.** O usuário pode forçar um caminho mais completo; o `aisef_new` recusa descer, e o check acusa `TRIAGE-OVERRIDDEN-DOWN` e `TRIAGE-LEAN-SHAPE`.

## Consequências

- O gateway não muda: a triagem altera os portões do processo, nunca as permissões.
- Errar a triagem para baixo é o risco principal. Por isso todo sinal sensível força `full`, o tamanho desconhecido também, e o perfil `team` continua como antes.
- O contrato guarda a triagem (`triage`), então o painel e a auditoria mostram por que uma feature foi enxuta.
