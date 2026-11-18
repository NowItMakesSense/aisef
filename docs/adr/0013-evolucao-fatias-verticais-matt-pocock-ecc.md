# ADR 0013: Evolução 0.6–0.9: fatias verticais, método do Matt Pocock e ideias do ECC

- **Status:** aceito
- **Data:** 2026-11-18

## Contexto

O uso real mostrou SDD/TDD fraco (tarefas fatiadas por papel), lentidão no despacho, painel sem visão do que os agentes fazem e falta de um modo só de perguntas.

## Decisão

- **Unidade de trabalho:** fatia vertical (tracer bullet) com `depends_on` como blocking edges. Especialistas viram revisores/consultores.
- **Matt Pocock (híbrido):** usar diretamente as skills que o modelo pode chamar (`tdd`, `grilling`, `domain-modeling`, `codebase-design`, `code-review`, `diagnosing-bugs`) e incorporar o método de `to-spec`, `to-tickets` e `implement-spec` às skills do AISEF, que guiam o usuário fase a fase.
- **ECC:** portar ideias, não instalar o plugin (hooks em Node duplicariam o gateway; suporte limitado no Windows).
- **Painel vivo** por servidor local, alimentado por `SubagentStart`/`SubagentStop`.
- **Frontend:** uma autoridade de design por projeto (`DESIGN.md` + tokens, aprovada como ADR) dentro da qual Impeccable, Taste e UI/UX Pro Max operam.

## Consequências

O detalhe de cada entrega está no [roadmap](../roadmap.md) e no CHANGELOG de cada versão.
