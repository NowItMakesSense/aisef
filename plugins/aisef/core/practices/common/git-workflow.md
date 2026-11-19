---
description: Commits e branches no AISEF
source: ECC rules/common/git-workflow.md (MIT), adaptado
---

# Git

- **Conventional Commits:** `<tipo>(<escopo>): <assunto no imperativo>` — tipos `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`, `build`. Corpo com o porquê e os ids da tarefa e dos requisitos. Quebra de compatibilidade com `!` e `BREAKING CHANGE:`.
- **Um commit, uma intenção:** nada de mudança não relacionada, arquivo gerado ou log de depuração misturado.
- **Nunca** `--no-verify`, nunca reescrever histórico publicado, nunca commitar segredo. Commit, push, PR e merge passam pelo Execution Gateway e precisam do OK do usuário.
- PR descreve o que mudou, por quê, como foi testado e o risco; considera o diff inteiro desde a base, não só o último commit.
