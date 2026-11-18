# ADR 0010: Roteamento de modelo e effort por tarefa

- **Status:** aceito
- **Data:** 2026-11-06

## Contexto

Usar o modelo mais caro em tudo é desperdício; usar o mais barato em tarefa arriscada gera retrabalho.

## Decisão

- Cada papel tem um padrão. O orquestrador ajusta por tarefa com sinais do Task Contract: risco, recursos sensíveis, tamanho e `complexity`.
- Uma escada única de níveis (L0 haiku/low a L6 opus/high). Cada tentativa que falha sobe um nível.
- Fable nunca é escolhido automaticamente.
- O validador roda num nível pelo menos igual ao do executor, de preferência em outro modelo.
- Variáveis de ambiente que anulam a escolha não são contornadas: o roteador avisa.

## Consequências

Política em `core/model-policy.v0.1.json`; o `aisef-check` acusa `ROUTE-VALIDATOR-WEAKER`.
