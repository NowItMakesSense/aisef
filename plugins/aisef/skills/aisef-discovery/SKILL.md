---
name: aisef-discovery
description: 'Descoberta de projeto do AISEF - investiga antes de perguntar e consolida em .aisef/discovery.md o que se sabe (com fonte) e o que falta, para projeto novo, projeto existente ou Impact Analysis de uma feature nova. Use depois do aisef-init, quando o usuario quiser "entender o projeto", "levantar requisitos", "analisar impacto" de uma mudanca, ou quando faltar informacao para escrever um Feature Contract.'
---

# aisef-discovery

Regra central (decisao explicita do usuario): **investigue antes de perguntar e nunca invente regra de negocio.**

## Ordem de investigacao
1. Documentacao do repositorio (README, docs/, ADRs, `.aisef/` existente).
2. Codigo e configuracoes (estrutura, modulos, rotas, telas, dependencias).
3. Schema de dados **sem conectar ao banco**: migrations, entidades, ORM, arquivos de schema. Diga claramente o que nao da para saber assim (regra T5).
4. Testes existentes e CI.
5. Historico relevante: `git log`, `git blame` (leitura e permitida).
6. Internet, quando a duvida for sobre tecnologia (cite a fonte).

Use subagentes `Explore` para varreduras amplas e leia so o necessario.

## O que levantar
- **Projeto novo**: problema, dores, publico-alvo, objetivos, escopo, requisitos funcionais e nao funcionais, regras de negocio, excecoes, features, dependencias, backend, frontend, banco, infraestrutura, seguranca, arquitetura, design system, UX e fluxos, integracoes, pagamentos (se houver), testes e qualidade.
- **Projeto existente**: o mesmo, mas extraido do que ja existe, mais funcionalidades existentes, decisoes anteriores e divida tecnica que afete o pedido.
- **Impact Analysis**: APIs, telas, componentes, tabelas, modulos, integracoes, dependencias, riscos, compatibilidade e possiveis regressoes. Avalie primeiro se a arquitetura atual comporta a mudanca.

## Classifique cada informacao
`confirmado pelo usuario` | `encontrado` (com caminho/linha ou URL) | `inferido` (com o raciocinio, precisa de confirmacao) | `desconhecido`.
So `confirmado` e `encontrado` podem virar requisito (`user_stated` / `investigated`). `inferido` vira pergunta.

## Perguntas
Pergunte so depois de investigar, uma de cada vez, explicando o que falta, o que ja encontrou e, quando fizer sentido, caminhos de investigacao. Quando o usuario nao conhecer uma tecnologia, explique: o que e, para que serve, como funciona, quando usar e evitar, vantagens, desvantagens, custos, consequencias arquiteturais e alternativas. Preferencia do usuario por uma tecnologia nao e requisito.

## Saida
Grave `.aisef/discovery.md` com secoes: Visao, Requisitos (com origem), Regras de negocio, Arquitetura atual ou proposta, Dados, Integracoes, Seguranca, Testes, Riscos, Desconhecidos, Fontes. Registre o marco:
```
python -I <skill-dir>/../../core/aisef_project.py append --project . --type evidence_recorded --summary "Discovery atualizado"
```
Depois siga com **aisef-feature** para a primeira feature.
