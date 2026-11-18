# ADR 0018: Modo Ask e revisão periódica de ferramentas

- **Status:** aceito
- **Data:** 2026-11-18

## Contexto

O usuário quer:
- um modo de só perguntar, como o Ask do Cursor, que gaste menos e em que o agente nunca execute nada diante de uma dúvida;
- que o AISEF saiba quando procurar skills e revise periodicamente custo e benefício, apagando o que não serve.

## Decisão

- **Modo Ask em duas formas:**
  - `/aisef:ask`: subagente Haiku, só `Read`/`Grep`/`Glob`, para uma pergunta;
  - `/aisef:modo ask`: estado da sessão em `.aisef/session/mode.json`, protegido como decisão do usuário. O gateway nega escrita, shell que não seja de leitura e MCP fora do `mcp_allow`, e um hook `UserPromptSubmit` lembra o modelo a cada pergunta.
- **Busca de ferramentas por gatilho**, não espontânea: fim da discovery, feature com tecnologia nova, fatia travada por tecnologia desconhecida, pedido do usuário.
- **Revisão periódica** (padrão: a cada feature aceita; o `next` avisa com `tooling_review_due`):
  - o usuário roda o `/skill-doctor` (o modelo não executa comandos de barra) e o AISEF interpreta;
  - `claude plugin eval --ablation with-without` mede o benefício, só com o OK do usuário e com teto de custo;
  - remover ou desinstalar é sempre decisão do usuário, e o gateway pede aprovação.

## Consequências

Nada é apagado automaticamente: usos = 0 nunca é prova suficiente sozinha (uma skill nova ou sazonal pode ainda não ter sido usada). A medição de benefício tem custo real de modelo e, no Windows, exige WSL para casos com Bash.
