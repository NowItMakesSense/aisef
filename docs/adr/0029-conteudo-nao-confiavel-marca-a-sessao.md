# ADR 0029: Conteúdo não confiável marca a sessão

- **Status:** aceito
- **Data:** 2026-11-25
- **Ajusta:** [ADR 0027](0027-gateway-e-camada-o-sandbox-e-a-fronteira.md)

## Contexto

Uma página lida pelo WebFetch, um resultado do WebSearch ou a resposta de um servidor MCP pode trazer instruções
escondidas (prompt injection). O vazamento acontece quando três coisas se juntam na mesma sessão, a "lethal trifecta":
acesso a dado privado, conteúdo não confiável e um canal de saída. O agente sempre tem a primeira (lê o repositório),
então o gateway só pode agir nas outras duas.

## Decisão

- Um hook `PostToolUse` síncrono em `WebFetch`, `WebSearch` e `mcp__*` grava uma marca por sessão em
  `.aisef/runtime/untrusted/<sessão>.json`. MCP no `mcp_allow` ou com confiança ativa (`aisef_mcp.py trust`) não marca.
- Enquanto a marca vale, o gateway:
  - sobe um nível a saída de dados com arquivo (`curl -d @`, `scp`, `-InFile`...): de pergunta para aprovação reforçada;
  - sobe um nível a escrita em config/CI/IaC: a autorização de escopo deixa de cobrir, vira pergunta;
  - pergunta antes de qualquer comando de rede (`curl`, `wget`, `ssh`, `Invoke-RestMethod`...), inclusive dentro de
    `bash -c` e `$(...)`.
- A marca vence sozinha: 60 minutos, ou `untrusted_ttl_minutes` no `.aisef/config.json`. Ler de novo renova.
- Apagar ou reescrever a marca (ou a pasta `.aisef/runtime`) é decisão do usuário. Marca ilegível conta como marca.

## Consequências

Depois de uma pesquisa na web, o `curl` do agente pergunta por uma hora. O WebFetch em si não é endurecido (uma URL
com dados na query também é saída); isso fica para o sandbox, que filtra rede por domínio. Um script Python que abre
conexão não é visto pelo gateway: de novo, só o sandbox fecha esse caso.
