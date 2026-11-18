---
name: aisef-panel
description: 'Abre o painel do AISEF, ao vivo: o que os agentes estao fazendo agora (tarefa, tempo, ultima acao), em que fase o projeto esta e o proximo passo, o fluxo de cada feature, as ondas paralelas no tempo, features, fatias, rastreabilidade de requisitos (RTM), aprovacoes, decisoes, riscos e dependencias, tudo em diagramas Mermaid e derivado dos contratos e do log com verificacao de integridade. Use quando o usuario quiser "ver o painel", "o que os agentes estao fazendo", "status do projeto", "o que esta pendente", "acompanhar a feature".'
---

# aisef-panel

CORE = `<skill-dir>/../../core`. O painel é uma **visão derivada**: nunca é fonte de verdade e é regenerado a partir dos contratos, do log e dos eventos dos subagentes.

## Ao vivo (padrão)
Suba o servidor local em segundo plano (Bash com `run_in_background: true`) e passe o endereço ao usuário:
```
python -I CORE/build_panel.py --project .aisef --out .aisef/panel --serve --open
```
- Ele escuta só em `127.0.0.1:8765` (`--port` muda a porta).
- Regenera os dados quando `.aisef/` muda, e a página se atualiza sozinha a cada 3 segundos.
- A aba **Agora** mostra:
  - a fase e o próximo passo (do `next`);
  - os subagentes em execução, com a fatia, o tempo e a última ação (hooks `SubagentStart`/`SubagentStop`);
  - o fluxo de cada feature, com a etapa atual destacada;
  - as ondas no tempo real (Gantt), que mostram o paralelismo.
- Para parar, encerre o processo em segundo plano.

## Estático (sem servidor)
```
python -I CORE/build_panel.py --project .aisef --out .aisef/panel --with-page
```
Depois abra `.aisef/panel/index.html` (`start` no Windows, `open` no macOS, `xdg-open` no Linux). Não se atualiza sozinho.

## Sempre
- `.aisef/panel/` e `.aisef/runtime/` estão fora do Git.
- Contratos inválidos ficam fora das visões e aparecem em `source_errors`: reporte e sugira **aisef-check**.
- Banner vermelho de integridade comprometida: pare e avise o usuário antes de qualquer outra coisa.
- O Mermaid (versão fixa, conferida por SHA-256) é baixado uma vez para `~/.aisef/vendor/`; dali em diante funciona offline.
- O painel só mostra. Decisões são tomadas pela **aisef-approve**; a aba Aprovações traz o que está pendente.
