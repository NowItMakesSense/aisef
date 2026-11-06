# Ciclo de vida AISEF (detalhe)

## Projeto novo
1. **aisef-init** cria `.aisef/` e o log de auditoria.
2. **aisef-discovery** conduz a descoberta (problema, dores, publico, objetivos, escopo, requisitos funcionais e nao funcionais, regras de negocio, excecoes, integracoes, seguranca, dados, UX, testes).
   Ao final, **aisef-tooling** sugere skills, plugins e MCPs ligados ao discovery; so instala o que o usuario escolher.
3. Decisoes de stack e arquitetura sao contextualizadas (modelo de dados, consistencia, operacao, custos, conhecimento da equipe...). Explique o que e, para que serve, quando usar e evitar, pros, contras, custos e alternativas. Arquitetura evolutiva: resolva o necessario agora e registre as decisoes (ADR no blueprint).
4. Para cada feature: Feature Contract -> Blueprint -> Tasks (skill **aisef-feature**).

## Projeto existente
Nao reconstrua nada. Primeiro investigue estrutura, codigo, arquitetura, features existentes, schemas e migrations (sem conectar ao banco), docs, testes, dependencias e decisoes anteriores. Registre em `.aisef/discovery.md` o que encontrou, com a fonte, e o que segue desconhecido. Depois identifique o que realmente precisa mudar.

## Impact Analysis (feature nova em projeto existente)
APIs, telas, componentes, tabelas, modulos, integracoes, dependencias, riscos, compatibilidade e possiveis regressoes. Avalie primeiro se a arquitetura atual comporta a necessidade.

## Planning
Investigacao, especificacao, decisoes, dependencias, tarefas e criterios de aceite. O usuario aprova por fluxo, feature ou requisito, conforme o plano.

## Execution
Implementacao, testes, revisao e documentacao. Contexto progressivo para cada agente:
- **obrigatorio**: Task Contract, requisitos ligados, decisoes aprovadas que afetam a tarefa;
- **referenciado**: caminhos de docs e codigo relevantes (com origem e versao);
- **sob demanda**: o resto, que o agente pede ao orquestrador.

## Priorizacao
Dependencias, bloqueios, impacto na entrega, risco tecnico e prioridade do usuario. Voce pode reorganizar a fila tecnica, nunca a prioridade de negocio sem autorizacao.

## Retomada apos interrupcao
Recupere o estado (contratos, relatorios, log), identifique tarefas interrompidas, verifique alteracoes parciais (`git status`/`git diff`), revalide permissoes e dependencias e retome do ultimo ponto seguro. Operacoes nao idempotentes exigem reconciliacao antes de repetir.

## Feature Acceptance
O encerramento exige: requisitos rastreados, criterios verificados, testes de integracao e regressao executados, documentacao atualizada, ausencia de pendencias ocultas, seguranca e permissoes verificadas e relatorio final planejado x executado (atendidos, nao atendidos, arquivos, testes, evidencias, decisoes, riscos, pendencias). O aceite **nao** autoriza commit, push, merge nem release.

## Arena (segunda opiniao)
Quando houver conflito ou decisao importante, ou o usuario pedir: rode um debate (defensor da solucao atual, challenger, especialista de dominio, revisor independente) com subagentes separados e entregue relatorio com argumentos, evidencias, alternativas, riscos, incertezas e recomendacao. Nao e votacao; a palavra final e do usuario.
