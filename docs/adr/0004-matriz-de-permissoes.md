# ADR 0004: Matriz de permissões

- **Status:** aceito
- **Data:** 2026-11-05

## Contexto

Agentes autônomos precisam de limites claros sobre Git, segredos, banco, configuração e produção.

## Decisão

- **Produção:** só com aprovação reforçada, de uso único, válida por no máximo 30 minutos, com diff, rollback e justificativa. Nunca por escopo.
- **Config, CI e IaC:** aprovação por escopo em dev e staging; reforçada em produção.
- **DML em staging** depende do dataset: sintético por escopo; anonimizado e verificado por escopo na escrita e por operação na leitura de linhas; não verificado ou real é tratado como produção.
- **Leitura de código e schema em produção:** aprovação por operação.
- **Git:** status, log e diff livres. Commit, push, pull request, merge e release pedem, cada um, a própria aprovação. Force push, reescrita de histórico e exclusão de branch exigem aprovação reforçada. *Ajustado pelo [ADR 0025](0025-git-por-risco.md): commit e preparo do commit numa branch de feature são livres, e o push dela é coberto pelo escopo da feature.*
- **Regras transversais:** T1 (operação destrutiva sobe um nível), T2 (produção é sempre pontual), T3 (segredo nunca em log), T4 (acesso ao schema não implica acesso aos dados), T5 (o AISEF funciona sem banco conectado).
- Autorização de escopo vale no máximo 7 dias. Em conflito, vale a regra mais restritiva; recurso ou ambiente não classificado é tratado como sensível ou produção.

## Consequências

A política está em `core/permission-policy.v0.1.json` e é aplicada pelo gateway (ADR 0008). `.aisef/policy.local.json` só pode endurecê-la.
