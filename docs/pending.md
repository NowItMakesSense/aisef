# Pendências

Nada aqui bloqueia o uso do plugin. Cada item precisa de uma decisão sua ou de trabalho futuro.

## Decisões suas
- [ ] **Rotação de chaves do Audit Signer.** O verificador já aceita vários `key_id` e chaves revogadas.
- [ ] **Ancoragem externa do head** (opção B), como reforço da assinatura.

## Trabalho futuro
- [ ] Interface visual do Approval Center. Hoje as decisões são tomadas pelo chat (skill `aisef-approve`).
- [ ] Registrar no log as tentativas que o gateway bloqueou ou pediu aprovação. Hoje só as operações executadas vão para o log.
- [ ] Ícone do plugin, que é opcional no diretório de plugins.

## Concluído em 2026-11-05
- Lista T1 ampliada.
- Validade máxima de 7 dias para autorizações de escopo.
- Painel com integridade comprometida: continua mostrando os dados, com o banner.
- O validador só usa Git de leitura.
- Um agente só fica `active` com a sua aprovação.
- Agent Contracts dos 8 agentes gerados no `aisef-init`, e o gateway aplica o teto de cada subagente.
- Novos testes no `check_project`: `PAR-FILE-CONFLICT`, `PAR-PATH-OVERLAP` e `REPORT-CONSULTATIONS`.
- Painel: aba Engenharia lendo o blueprint, e Mermaid funcionando offline com uma cópia local.
