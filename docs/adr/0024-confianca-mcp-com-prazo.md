# ADR 0024: Confiança em ferramentas MCP, com prazo

- **Status:** aceito
- **Data:** 2026-11-20

## Contexto

Uma ferramenta MCP fora do `mcp_allow` do `config.json` pedia aprovação a cada chamada. O `mcp_allow` resolvia isso, mas não tinha prazo, e um glob como `mcp__docs__*` cobria também uma ferramenta do servidor que executa código. A autorização de escopo existente é presa a uma feature e à matriz da política, e a confiança numa ferramenta vale para o projeto inteiro.

## Decisão

- Novo tipo de autorização, `mcp_tool`, em `.aisef/authorizations/MCP-NNN.json`: ferramentas (nomes ou globs), `allow_code_execution` e validade de no máximo `validity_max_days` da política (7 dias). Renovar é criar outra.
- `core/aisef_mcp.py trust|revoke|list`. `trust` e `revoke` são decisão do usuário: o gateway abre o prompt nativo, e cada uma vira `authorization_granted` ou `authorization_revoked` no log assinado.
- O gateway deixa passar a ferramenta coberta por uma confiança ativa e no prazo. Quando pergunta, a mensagem traz o comando para confiar.
- **Ferramenta que executa código ou comandos** (padrão `mcp_code_execution` em `sensitive_patterns.json`) nunca entra por glob, nem no `mcp_allow` nem numa confiança comum: só pelo nome exato no `mcp_allow` ou por confiança com `allow_code_execution`.
- O check valida o documento e acusa `AUTH-SCOPE-TOO-LONG`, `AUTH-HISTORY` e, como aviso, `AUTH-EXPIRED`.

## Consequências

- Menos prompts para ferramentas de leitura confiáveis, sem permissão eterna.
- Quem tinha um glob no `mcp_allow` cobrindo uma ferramenta que executa código passa a ver o prompt para ela. É de propósito.
- O modo Ask continua só com o `mcp_allow`: confiança com prazo não abre o modo só de leitura.
