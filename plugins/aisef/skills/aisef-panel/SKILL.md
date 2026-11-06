---
name: aisef-panel
description: 'Gera e abre o painel HTML do AISEF (visao geral, features, tarefas, rastreabilidade RTM, aprovacoes, decisoes, agentes, riscos, linha do tempo e dependencias em Mermaid), derivado dos contratos e do log de auditoria e com verificacao de integridade. Use quando o usuario quiser "ver o painel", "status do projeto", "o que esta pendente", "acompanhar a feature".'
---

# aisef-panel

CORE = `<skill-dir>/../../core`. O painel e uma **visao derivada**: nunca e fonte de verdade, e regenerado a cada vez.

```
python -I CORE/build_panel.py --project .aisef --out .aisef/panel --with-page
```
Depois abra `.aisef/panel/index.html` no navegador (`start` no Windows, `open` no macOS, `xdg-open` no Linux). `.aisef/panel/` esta no `.gitignore` do AISEF.

- Contratos invalidos ficam fora das visoes e aparecem em `source_errors`: reporte-os e sugira **aisef-check**.
- Banner vermelho de integridade comprometida: pare e avise o usuario antes de qualquer outra coisa.
- O Mermaid (versao fixa, conferida por SHA-256) e baixado uma vez para `~/.aisef/vendor/` e copiado para o painel; dali em diante funciona offline. Sem rede e sem cache, a pagina tenta a CDN e, se falhar, mostra o codigo dos diagramas.
- O painel so mostra. Decisoes sao tomadas pelo **aisef-approve**.
