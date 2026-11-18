# ADR 0008: Plugin do Claude Code com Execution Gateway

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

Skills sozinhas só pedem ao modelo que se comporte. Para aplicar a política, é preciso um ponto de controle técnico em cada chamada de ferramenta.

## Decisão

- O AISEF é um plugin distribuído por marketplace no GitHub. O código fica no plugin e os dados ficam em `.aisef/` no projeto.
- O gateway é um hook `PreToolUse`. As aprovações usam o prompt nativo de permissão (`ask`), que o modelo não consegue responder.
- Nível reforçado sem registro aprovado para a operação exata resulta em `deny`.
- Banco a partir de uma sessão: o ambiente alvo é desconhecido e a política o trata como produção.
- Regras nativas de segunda camada são `ask`, não `deny`, para não impedir o que a política permite com aprovação.
- O AISEF é independente da skill `new-project-setup`; não absorve nada dela.

## Consequências

O gateway não é uma fronteira de segurança: lê comandos por padrões e deve ser usado com o sandbox do Claude Code. Desde a v0.5.2 cobre Bash e PowerShell.
