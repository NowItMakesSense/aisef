# Roadmap

O detalhe de cada versão entregue está no [CHANGELOG](../CHANGELOG.md); as decisões, nos [ADRs](adr/README.md).

## Próximas versões

| Versão | Entrega |
|---|---|
| ~~0.6.0~~ | Entregue: SDD + TDD com fatias verticais, `implementer`, evidência de TDD checada e guia de fases |
| ~~0.6.1~~ | Entregue: autoridade de design por projeto, `design_check` e frontend dentro dos tokens |
| ~~0.7.0~~ | Entregue: `dispatch` da onda numa chamada, validação por onda, `precheck` determinístico, auditoria assíncrona das edições |
| depois | **Worktrees por fatia** (fatias com arquivos em comum em paralelo). Adiado: pela política atual, cada merge local pede aprovação; antes é preciso uma autorização de escopo para merges em branches de integração (mudança de política, decisão sua) |
| ~~0.8.0~~ | Entregue: painel ao vivo (servidor local), aba Agora, fluxo da feature, ondas em Gantt, estado efetivo |
| ~~0.8.1~~ | Entregue: aprendizado contínuo revisado e estado que sobrevive ao compact. Perfis de hook descartados (o gateway precisa rodar sempre) |
| ~~0.8.2~~ | Entregue: busca de ferramentas por gatilho, revisão periódica (`/skill-doctor`, `claude plugin eval`), desinstalação com aprovação |
| ~~0.9.0~~ | Entregue: modo Ask (`/aisef:ask` em Haiku só de leitura e `/aisef:modo ask` aplicado pelo gateway) |

## Itens antigos de `pending.md`

| Item | Destino |
|---|---|
| Registrar no log as tentativas que o gateway bloqueou | Concluído na 0.2.0 |
| Ícone do plugin | Concluído |
| Rotação de chaves do Audit Signer | Concluído (`aisef_project.py rotate-key`) |
| Ancoragem externa do head | **Descartado:** a âncora local fora do repositório (`~/.aisef/anchors/`) cobre o uso individual, e uma âncora remota exigiria aprovação de push a cada checkpoint ([ADR 0005](adr/0005-log-de-auditoria-assinado-com-head-externo.md)) |
| Interface visual do Approval Center | Vira a aba "Decisões" do painel vivo (0.8.0): mostra as pendências com o comando pronto; a decisão continua no prompt nativo |
