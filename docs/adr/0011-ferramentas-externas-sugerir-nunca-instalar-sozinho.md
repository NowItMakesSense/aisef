# ADR 0011: Ferramentas externas: sugerir, nunca instalar sozinho

- **Status:** aceito
- **Data:** 2026-11-06

## Contexto

Skills, plugins e servidores MCP mudam o que o agente consegue fazer, mas reinventar o que já existe é desperdício.

## Decisão

- A skill `aisef-tooling` sugere a partir de fontes prontas: `find-skills` (skills.sh), o MCP Registry oficial e os marketplaces de plugins.
- Cada sugestão é ligada a uma necessidade do discovery e verificada (fonte, sinais, risco).
- Instalar pede aprovação no gateway, no escopo do projeto. O passo de instalação global da `find-skills` não é usado.
- Grafo por MCP externo: codebase-memory-mcp para o **código** e Graphify para **docs e decisões**. Só as ferramentas de leitura entram em `mcp_allow`.

## Consequências

O lembrete consultivo do grafo roda dentro do gateway para Grep e Glob, sem bloquear.
