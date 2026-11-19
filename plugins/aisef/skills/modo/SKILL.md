---
name: modo
description: 'Troca o modo da sessao AISEF: ask (so perguntas e leitura; o gateway nega qualquer edicao ou comando que mude algo) ou exec (normal). So o usuario troca.'
argument-hint: "ask | exec"
disable-model-invocation: true
---

Troque o modo da sessao para **$ARGUMENTS** (aceito: `ask` ou `exec`; outro valor: mostre o modo atual e explique os dois).

Rode exatamente:
```
python -I <skill-dir>/../../core/aisef_project.py mode --project . --set $ARGUMENTS
```
Entrar no `ask` e imediato (so restringe). Voltar ao `exec` abre o prompt nativo de permissao, porque devolve poder de execucao e e decisao do usuario. Depois, confirme em uma linha:
- **ask:** "Modo Ask: respondo lendo o projeto, sem editar nem executar nada. Para voltar: /aisef:modo exec."
- **exec:** "Modo normal: volto a executar dentro das regras do AISEF."

Sem argumento: rode `python -I <skill-dir>/../../core/aisef_project.py mode --project .` (so mostra o modo atual).
