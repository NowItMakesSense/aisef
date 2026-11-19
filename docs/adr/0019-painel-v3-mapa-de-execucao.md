# ADR 0019: Painel v3: mapa de execução e quem disparou quem

- **Status:** aceito
- **Data:** 2026-11-19

## Contexto

O painel da 0.9.2 mostrava os agentes como cartões grandes cheios de pílulas, e os diagramas vinham do Mermaid com cores fixas. Não dava para ver, num relance, o que estava rodando, o que estava esperando e por quê, nem quais subagentes cada agente tinha disparado. O usuário aprovou um protótipo (v3) e pediu que ele virasse o painel real.

## Decisão

- **O mapa de execução é a visão principal da tela Agora:** orquestrador à esquerda, uma coluna por onda, um nó por fatia com estado, tempo e a última ação; subagentes presos ao nó que os disparou; arestas que dizem se a dependência está ativa, satisfeita ou presa a uma decisão sua.
- **Estado por forma, ícone e cor:** rodando, validando, esperando outra fatia, esperando você, concluída, reprovada. Lê-se sem distinguir cores.
- **Quem disparou quem vem de um hook novo** (`PreToolUse` com matcher `Agent|Task`, em segundo plano). Ele grava o agente que chamou, o tipo do subagente, o pedido e o modelo. O painel liga cada registro ao `SubagentStart` seguinte do mesmo tipo; quando há mais de um candidato possível, a ligação aparece como **inferida**. A trilha assinada continua no log de auditoria: isto é uma visão efêmera em `.aisef/runtime/`.
- **O gateway grava o `agent_id`** de quem teve uma ferramenta negada, e o painel prende a negação à fatia exata.
- **Diagramas:** o grafo de dependências passa a ser desenhado pelo próprio painel (mesma linguagem do mapa, com o caminho crítico), e o fluxo da feature por diagrama sai (o stepper já mostra). Arquitetura e ER continuam no Mermaid, nas cores do tema.
- **Vidro só no que flutua** (barra do topo, gaveta, busca, barra inferior do celular). Os dados ficam em superfícies opacas para manter o contraste.
- **Busca global e atalhos** (`Ctrl K`, `/`, `g` + letra, `t`, `Esc`) e filtros que sobrevivem a recarregar a página.
- **Teste no navegador só com Python:** o `test_panel.py` abre a página no Chrome sem interface com `?selftest=1`; a própria página confere que nenhuma tela rola na horizontal em 375 px e que filtros, gaveta e rolagem sobrevivem a uma atualização ao vivo. Sem Chrome, essa parte é pulada.

## Consequências

- A regra de liberação não muda: uma fatia só libera a seguinte quando é concluída, depois de validada. O mapa mostra isso como "esperando outra fatia".
- Ainda falta confirmar numa sessão real que o Claude Code entrega o `agent_id` de quem chama a ferramenta Agent. Sem isso, toda ligação pai → subagente aparece como inferida, o que é honesto, mas menos útil.
- O painel continua sendo uma visão derivada (ADR 0007): nada nele é fonte de verdade.
