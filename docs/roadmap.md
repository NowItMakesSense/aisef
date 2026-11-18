# Roadmap

O detalhe de cada versão entregue está no [CHANGELOG](../CHANGELOG.md); as decisões, nos [ADRs](adr/README.md).

## Próximas versões

| Versão | Entrega |
|---|---|
| 0.6.0 | **SDD + TDD:** fases Grill → Spec → Fatias → Implementação com o método do Matt Pocock; fatias verticais; evidência de teste vermelho antes do verde; guia de próximos passos |
| 0.6.1 | **Frontend:** autoridade de design por projeto (`DESIGN.md` + tokens) com Impeccable, Taste e UI/UX Pro Max; critérios de aceite visuais |
| 0.7.0 | **Velocidade:** `dispatch` da onda numa chamada, validação por onda, `precheck` determinístico, worktrees opcionais |
| 0.8.0 | **Painel vivo:** servidor local, visão "Agora", fluxo da feature, ondas em Gantt, RTM viva |
| 0.8.1 | **Aprendizado contínuo revisado** e estado que sobrevive ao compact; perfis de hook |
| 0.8.2 | **Ciclo de vida das ferramentas:** busca por gatilho, revisão periódica com `/skill-doctor` e `claude plugin eval` |
| 0.9.0 | **Modo Ask:** pergunta em subagente Haiku só de leitura e modo fixo aplicado pelo gateway |

## Itens antigos de `pending.md`

| Item | Destino |
|---|---|
| Registrar no log as tentativas que o gateway bloqueou | Concluído na 0.2.0 |
| Ícone do plugin | Concluído |
| Rotação de chaves do Audit Signer | Concluído (`aisef_project.py rotate-key`) |
| Ancoragem externa do head | **Descartado:** a âncora local fora do repositório (`~/.aisef/anchors/`) cobre o uso individual, e uma âncora remota exigiria aprovação de push a cada checkpoint ([ADR 0005](adr/0005-log-de-auditoria-assinado-com-head-externo.md)) |
| Interface visual do Approval Center | Vira a aba "Decisões" do painel vivo (0.8.0): mostra as pendências com o comando pronto; a decisão continua no prompt nativo |
