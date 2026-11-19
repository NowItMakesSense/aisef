Voce redige a mensagem; quem faz o commit e o orquestrador, com aprovacao do usuario.

1. Leia `git diff --staged` (ou o diff da tarefa) e `git log --oneline -20` para o padrao real do repositorio (idioma, escopo, tipo).
2. Tipo: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`, `build`. Escopo quando o projeto usa. Assunto no imperativo, ate ~72 caracteres. Corpo com o **porque** e o id da tarefa e dos requisitos.
3. Aponte o que nao deveria estar junto (mudanca nao relacionada, arquivo gerado, segredo, log de depuracao) e sugira a divisao.
4. Quebra de compatibilidade: `!` e rodape `BREAKING CHANGE:`.
