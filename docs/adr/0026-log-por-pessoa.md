# ADR 0026: Um log de auditoria por pessoa

- **Status:** aceito
- **Data:** 2026-11-20
- **Complementa:** [ADR 0005](0005-log-de-auditoria-assinado-com-head-externo.md)

## Contexto

O log assinado é uma cadeia linear num arquivo só (`.aisef/audit/log.jsonl`), com uma chave por projeto. Quando duas pessoas trabalham em branches diferentes, cada uma anexa eventos com a mesma sequência. O merge conflita no arquivo, e qualquer resolução parte a cadeia. Além disso, a chave é da máquina de quem iniciou o projeto, então uma aprovação dada por outra pessoa não carrega a assinatura dela.

## Decisão

- **Opcional:** `config.json` → `"audit": {"streams": true, "owner": "<id>"}`, ligado por `aisef_streams.py enable`. É decisão do usuário: o gateway pergunta.
- **O dono:** o log que já existe vira o stream do dono, sem reescrever nada.
- **Cada outra pessoa ganha um stream em `.aisef/audit/streams/<id>/`:**
  - cadeia própria e `log_id` `<projeto>.<id>`;
  - chave Ed25519 própria (`<id>.audit-key-1`: a privada em `~/.aisef/keys/`, a pública em `.aisef/keys/`);
  - ids de evento `<id>.E<n>`;
  - `head.json` próprio, versionado.
- **Identidade:** `AISEF_USER`, senão o e-mail do Git.
- **Cada pessoa só anexa aos próprios arquivos**, então o merge não conflita no log.
- **Decisões:** uma decisão (aprovação, aceite) vai para o stream de quem decidiu, assinada pela chave dessa pessoa.
- **Leitura:** quem lê o log recebe os streams juntos, em ordem de tempo.
- **Verificação:**
  - o `verify`, o painel e a Action `aisef-verify` verificam stream a stream;
  - o check compara a ordem das correções pela posição e confere a ordem de tempo dentro de cada stream;
  - na PR, a Action exige que o último evento de cada stream da base continue lá, e apagar um stream conta como corte.

## Consequências

- Times podem trabalhar em paralelo sem quebrar a trilha de auditoria, e cada assinatura identifica a pessoa.
- O head externo de cada stream fica na máquina de quem grava. Na máquina do dono, o stream de outra pessoa sem o head dela gera aviso, não erro; no CI, vale o `head.json` versionado de cada stream.
- Checkpoint, âncora e rotação continuam só no stream do dono. Os streams das pessoas crescem até alguém precisar disso, o que vira outra decisão.
