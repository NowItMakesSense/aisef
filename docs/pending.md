# Pendências

Estes pontos não bloqueiam a v0.1. Cada um precisa de uma decisão sua ou de trabalho futuro.

## Decisões suas
- [ ] **Lista final de operações destrutivas (T1).** Hoje a lista inclui DROP, TRUNCATE, DELETE sem WHERE, `rm -r`, apagar branch e force push.
- [ ] **Validade máxima de uma autorização de escopo.** Hoje `valid_until` é obrigatório, mas sem teto. Sugestão: 7 dias.
- [ ] **Painel com integridade comprometida:** continuar mostrando os dados com o banner (comportamento atual) ou ocultar as visões?
- [ ] **Rotação de chaves do Audit Signer.** O verificador já aceita vários `key_id` e chaves revogadas.
- [ ] **Ancoragem externa do head** (opção B), como reforço da assinatura.
- [ ] **O validador só pode usar Git de leitura?** Foi proposto no chat e ainda não foi confirmado.
- [ ] **Agente `active` exige aprovação do usuário no Agent Contract?** Também proposto e ainda não confirmado.

## Trabalho futuro
- [ ] Páginas do painel que leem o blueprint: Backend, Frontend, Banco/ER, DevOps e Segurança.
- [ ] Interface visual do Approval Center. Na v0.1, as decisões são tomadas pelo chat (skill `aisef-approve`).
- [ ] Testes que faltam no `check_project`: conflito de arquivos entre tarefas paralelas e limite de consultas a especialistas.
- [ ] Agent Contracts para os 8 agentes do plugin, gerados no `aisef-init`. Hoje o hook registra subagentes em `data.subagent`, com ator `orchestrator`.
- [ ] Migrar o que falta da `new-project-setup`: grafo de conhecimento, CI gerado, time de front-end, `Database/` e templates de docs. Depois disso, remover a skill antiga de `~/.claude/skills/`.
- [ ] Fazer o Mermaid funcionar offline (cópia local em vez de CDN).
- [ ] Ícone do plugin, que é opcional no diretório de plugins.
