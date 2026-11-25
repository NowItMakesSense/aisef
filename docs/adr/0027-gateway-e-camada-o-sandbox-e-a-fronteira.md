# ADR 0027: O gateway é uma camada; a fronteira é o sandbox

- **Status:** aceito
- **Data:** 2026-11-25
- **Ajusta:** [ADR 0008](0008-plugin-do-claude-code-com-execution-gateway.md)

## Contexto

A análise de 2026-11-25 rodou o gateway num projeto de teste e passou sete comandos sem nenhuma pergunta: o nome da
pasta da chave partido por aspas, montado por variável ou coberto por curinga; um script que lê a chave, escrito agora
para rodar depois; deploy escondido em `npm run deploy`; `curl -d @.env`; e um hook do Git plantado em
`.git/hooks/`. O README dizia que nenhum contorno passava.

O gateway é um hook `PreToolUse` que roda com o mesmo usuário do sistema que o agente. Ele só vê a chamada de
ferramenta, não o que um programa faz depois. A doc oficial do Claude Code e o OWASP Top 10 for Agentic Applications
(2026) tratam esse tipo de hook como camada de política, e o isolamento como trabalho do sistema operacional.

## Decisão

- O gateway fecha os sete casos (S-03): aspas e escape são tirados antes de procurar o caminho da chave; variável e
  curinga perto da pasta do AISEF viram pergunta; texto escrito em arquivo que monta o caminho da chave na home
  pergunta; alvos `deploy`, `release`, `ship` e `publish` de scripts do projeto contam como deploy; envio de arquivo
  para fora pergunta, e com arquivo sensível é negado; escrever em `.git/hooks/`, `.githooks/` e `.claude/hooks/` é
  `config_ci_iac`.
- O que o gateway não consegue provar vira pergunta, nunca liberação. Negação só quando há certeza.
- A fronteira de verdade é o sandbox nativo do Claude Code ou um devcontainer. Os perfis `team` e `regulated` passam a
  exigir um deles (S-04).
- O README diz o que o gateway não garante.

## Consequências

Alguns comandos legítimos passam a perguntar (`make release`, `scp` para um servidor, curinga na home). O corpus guarda
casos legítimos para pegar regressão. `python script.py` depois de um Write que não cita a chave continua livre: só o
sandbox fecha esse caso.
