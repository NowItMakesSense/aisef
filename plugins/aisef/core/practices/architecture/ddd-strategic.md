---
description: DDD estrategico - contextos delimitados, linguagem ubiqua, context map
source: AISEF
---

# DDD estratégico

Vale para quase todo sistema com mais de uma área de negócio, mesmo sem DDD tático.

- **Linguagem ubíqua:** os termos do negócio, com significado preciso, iguais no código, nos testes, na spec e na conversa. Mantenha um glossário (`CONTEXT.md` ou `docs/glossary.md`); a skill `domain-modeling` e o agente `domain` ajudam.
- **Contexto delimitado (bounded context):** fronteira onde um modelo e uma linguagem valem. "Cliente" em Vendas ≠ "Cliente" em Cobrança — modelos diferentes, não um modelo gigante compartilhado.
- **Subdomínios:** *core* (diferencial, onde investir DDD tático), *supporting* (necessário, específico) e *generic* (compre ou use pronto: autenticação, pagamento, e-mail).
- **Context map:** como os contextos se relacionam — cliente/fornecedor, conformista, **camada anticorrupção** (traduz o modelo externo para o seu), *shared kernel* (pequeno e com dono duplo), *open host service* / *published language* (API pública estável).
- **Integração entre contextos:** por API pública ou evento; nunca lendo a tabela do outro contexto.

## Sinais de problema
A mesma palavra com significados diferentes no mesmo módulo; "modelo canônico" único para a empresa; módulo que importa o interior de outro; *shared kernel* que cresce sem dono.

## Quando não usar
Sistema pequeno com um só domínio: um glossário basta; contextos formais ficam para quando aparecer uma segunda área com linguagem própria.
