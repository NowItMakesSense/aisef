# ADR 0022: Revisores escolhidos em código e gates portados do ECC

- **Status:** aceito
- **Data:** 2026-11-19

## Contexto

Com 66 papéis, escolher revisores "de cabeça" a partir de uma regra em texto na skill não escala nem é verificável. O ECC tem ideias úteis:
- revisão com filtro de confiança;
- revisão dupla independente (santa-method);
- `verification-loop`;
- proteção de config de lint;
- bloqueio de `--no-verify`.

## Decisão

- **`core/aisef_review.py`** calcula os revisores de cada tarefa:
  - geral;
  - linguagem e framework;
  - dados;
  - segurança em risco alto;
  - arquitetura;
  - testes.
  
  O `aisef_new` grava `review.reviewers` no Task Contract. O `validate-wave` despacha os revisores pendentes em paralelo **antes** do validador.
  - Só `APPROVE` de todos libera o validador; `WARNING` e `BLOCK` reprovam.
  - Em risco alto, dois `code-reviewer` independentes, em níveis de modelo diferentes.
  - Revisor sem Agent Contract ativo não entra e é listado como sugestão. Tarefa antiga, sem `review`, não muda.
- **Gateway:**
  - escrever em config de lint, formatação ou tipos exige `config_ci_iac`;
  - `--no-verify`, `--no-gpg-sign` e `-c commit.gpgsign=false` no Git são sempre negados;
  - subagente do catálogo sem Agent Contract não edita.
- **`verify-loop`** (`core/aisef_verify.py`): build, tipos, lint, testes, segredos no diff e resumo, com evidência por tarefa. Os comandos vêm do mapeamento do plugin ou do `config.json`, nunca do modelo.
- **Não portados:** o `gateguard` fact-force (sobrepõe o gateway; fica para avaliação), o hookify e os perfis de hook (ADR 0017).

## Consequências

- **Custo:** cada fatia passa a gastar mais chamadas de modelo, uma por revisor. A medição com e sem a equipe nova (`bench_outcomes.py`, pass@k) está na lista de avaliação. Se o custo pesar, o brief pode fixar menos revisores por tarefa.
- **Projetos que mudam lint como parte de uma tarefa:** a tarefa precisa ir ao `devops` ou ao orquestrador, que têm `config_ci_iac`.
