# Modo Ask

O Claude Code não tem um "Ask" como o do Cursor, e plugins não podem criar modos de permissão. O AISEF oferece dois caminhos:

| | `/aisef:ask <pergunta>` | `/aisef:modo ask` |
|---|---|---|
| Para quê | Uma pergunta avulsa | Uma sessão inteira de perguntas |
| Quem responde | Subagente `aisef:ask`: Haiku, effort baixo, só `Read`/`Grep`/`Glob` | A sessão normal |
| Garantia de não mudar nada | O agente não tem ferramenta de escrita nem de shell | O gateway nega escrita, shell que não seja de leitura e MCP fora do `mcp_allow` |
| Custo | Baixo (Haiku) | O modelo da sessão |
| Como sair | Não precisa | `/aisef:modo exec` (abre o prompt nativo) |

Por que dois:
- `model: haiku` numa skill normal vale **só para aquele turno**. A economia real vem de rodar a pergunta num subagente barato e só de leitura.
- Para uma conversa longa de dúvidas, o modo fixo é mais prático, e a garantia vem do gateway, não da boa vontade do modelo.

O modo plan nativo do Claude Code (`Shift+Tab`) também serve para conversar sem editar, mas ele foi feito para planejar antes de executar.

**A confirmar no seu Claude Code:** `/aisef:ask` usa `context: fork` com `agent: aisef:ask`. A documentação oficial cita agentes de `.claude/agents/` e os embutidos; se a sua versão não resolver o agente do plugin, o fork cai no `general-purpose`, que pode editar. Para garantia total, use `/aisef:modo ask`.
