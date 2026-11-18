---
name: ask
description: 'Modo pergunta do AISEF (como o Ask do Cursor): responde uma duvida sobre o projeto lendo o codigo e os contratos, num subagente Haiku so de leitura, sem editar nem executar nada. Use quando o usuario digitar /aisef:ask ou fizer uma pergunta e pedir explicitamente para nao mudar nada.'
argument-hint: "<sua pergunta>"
context: fork
agent: aisef:ask
model: haiku
effort: low
---

Responda a pergunta abaixo sobre este projeto. **Voce so le**: nao edite arquivos e nao rode comandos que mudem algo (nem tem as ferramentas para isso).

Pergunta: $ARGUMENTS

Como responder:
1. Procure primeiro onde a resposta mora:
   - `.aisef/discovery.md`, `.aisef/contracts/` (features, fatias, requisitos), `.aisef/design/` e `.aisef/knowledge/`;
   - os docs;
   - o codigo, com Grep e Glob antes de abrir arquivos inteiros.
2. Responda direto, em poucas linhas, citando `arquivo:linha` ou o id do contrato (FEAT-, T-, REQ-) de onde tirou cada ponto.
3. Separe o que **encontrou** do que esta **inferindo**. O que nao estiver documentado, diga que nao esta: nunca invente regra de negocio.
4. Se a resposta for "isso exige uma mudanca", descreva a mudanca em uma frase e diga que, para executar, o usuario pede a mudanca normalmente (ou troca o modo com `/aisef:modo exec`).
