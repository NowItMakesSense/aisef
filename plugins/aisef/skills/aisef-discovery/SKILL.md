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

Use subagentes `Explore` (ou `aisef:code-explorer`, quando ativo) para varreduras amplas e leia so o necessario.

## Deteccao de stack e arquitetura (projeto existente, e Impact Analysis)
1. Rode `python -I <skill-dir>/../../core/aisef_project.py detect --project .` (atualiza `.aisef/architecture.json` e cria os drafts dos agentes da stack).
2. **Confirme o estilo, nao o assuma.** Nome de pasta nao prova arquitetura: abra 2 ou 3 arquivos de cada camada citada na evidencia e veja se o codigo segue o estilo (dominio sem framework, casos de uso orquestrando, adaptadores na borda). Diga ao usuario o que confirmou e o que nao.
3. **Apresente as recomendacoes** (`recommendations`), uma por vez, com o porque, o impacto e o esforco. Quando o usuario nao conhecer o estilo, explique-o com a pratica do plugin (`core/practices/architecture/<estilo>.md`), inclusive **quando nao usar**. Nao recomende DDD tatico, CQRS ou microsservicos a um CRUD simples.
4. **Adocao e decisao do usuario.** Para o estilo que ele adotar (o atual ou o alvo), abra um pedido `architecture_decision` (skill **aisef-approve**) com a proposta de ADR (o agente `architect` pode redigir). Aprovado, registre:
   `python -I <skill-dir>/../../core/aisef_project.py detect --project . --adopt clean,ddd-tactical --request REQ-xxx`
   Isso ativa os papeis por arquitetura e faz o `architecture-reviewer` cobrar o estilo nas entregas.
5. Violacoes da regra de dependencia (`aisef_detect.py deps`) entram em "Divida tecnica" e, se o usuario quiser, viram feature de refatoracao.
6. **Boas praticas:** proponha instalar as praticas aplicaveis (`practices` do architecture.json) em `.claude/rules/aisef/`: `python -I <skill-dir>/../../core/aisef_project.py practices --project .` mostra o que entraria; `--apply` grava com o OK do usuario.
7. **Projeto existente sem documentacao** de uma area critica: o `spec-miner` extrai os comportamentos atuais (QUANDO/ENTAO) antes de qualquer mudanca.
8. **Antes de construir, procure o que ja existe** (search-first): biblioteca, skill, MCP ou servico que resolva 80% do problema. Registre o achado como opcao (adotar, estender ou construir) no discovery.

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
Grave `.aisef/discovery.md` com secoes: Visao, Requisitos (com origem), Regras de negocio, Arquitetura atual ou proposta (estilo detectado, confirmado e adotado; violacoes; recomendacoes e decisoes), Boas praticas adotadas, Dados, Integracoes, Seguranca, Testes, Riscos, Desconhecidos, Fontes. Registre o marco:
```
python -I <skill-dir>/../../core/aisef_project.py append --project . --type evidence_recorded --summary "Discovery atualizado"
```
Em projeto novo ou existente, rode em seguida a **aisef-tooling** para sugerir skills, plugins e MCPs a partir do
discovery (na Impact Analysis, so se o usuario pedir). Se o projeto tem interface e ainda nao ha `.aisef/design/tokens.json` aprovado, rode a **aisef-design** antes da primeira feature de UI. Depois siga com **aisef-feature** para a primeira feature.
