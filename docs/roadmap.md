# Roadmap

O detalhe de cada versão entregue está no [CHANGELOG](../CHANGELOG.md); as decisões, nos [ADRs](adr/README.md).

## Próximas versões

| Versão | Entrega |
|---|---|
| ~~0.6.0~~ | Entregue: SDD + TDD com fatias verticais, `implementer`, evidência de TDD checada e guia de fases |
| ~~0.6.1~~ | Entregue: autoridade de design por projeto, `design_check` e frontend dentro dos tokens |
| ~~0.7.0~~ | Entregue: `dispatch` da onda numa chamada, validação por onda, `precheck` determinístico, auditoria assíncrona das edições |
| ~~depois~~ | Entregue na 0.14.0 (L-02): worktrees por fatia, com o merge da fatia coberto pelo escopo da feature (ADR 0025) |
| ~~0.8.0~~ | Entregue: painel ao vivo (servidor local), aba Agora, fluxo da feature, ondas em Gantt, estado efetivo |
| ~~0.8.1~~ | Entregue: aprendizado contínuo revisado e estado que sobrevive ao compact. Perfis de hook descartados (o gateway precisa rodar sempre) |
| ~~0.8.2~~ | Entregue: busca de ferramentas por gatilho, revisão periódica (`/skill-doctor`, `claude plugin eval`), desinstalação com aprovação |
| ~~0.9.0~~ | Entregue: modo Ask (`/aisef:ask` em Haiku só de leitura e `/aisef:modo ask` aplicado pelo gateway) |
| ~~0.9.3~~ | Entregue: o Ask pesquisa na internet com fontes e escolhe o modelo pela pergunta |
| 0.11.0 | Medir: `metrics`, benchmark de resultado, tokens por subagente, Graphify padrão (PR #17) |
| 0.12.0 | Trilha E ([plano](plan/trilha-e-ecc.md)): 66 agentes num catálogo, detecção de stack e arquitetura, boas práticas, revisores em código, `verify-loop`. Lista de avaliação na seção 3 do plano |
| ~~0.10.0~~ | Entregue: painel v3 (mapa de execução, raias em paralelo, quem disparou quem, gaveta do agente, grafo de dependências com caminho crítico, busca e atalhos) |
| depois | Confirmar numa sessão real que o Claude Code entrega o `agent_id` de quem chama a ferramenta Agent; sem isso, a ligação pai → subagente continua marcada como inferida |

## Itens antigos de `pending.md`

| Item | Destino |
|---|---|
| Registrar no log as tentativas que o gateway bloqueou | Concluído na 0.2.0 |
| Ícone do plugin | Concluído |
| Rotação de chaves do Audit Signer | Concluído (`aisef_project.py rotate-key`) |
| Ancoragem externa do head | **Descartado:** a âncora local fora do repositório (`~/.aisef/anchors/`) cobre o uso individual, e uma âncora remota exigiria aprovação de push a cada checkpoint ([ADR 0005](adr/0005-log-de-auditoria-assinado-com-head-externo.md)) |
| Interface visual do Approval Center | Vira a aba "Decisões" do painel vivo (0.8.0): mostra as pendências com o comando pronto; a decisão continua no prompt nativo |
