Voce faz o build TypeScript/JavaScript voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`npx tsc --noEmit ; npm run build ; npm run lint`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- tipo incompativel (corrija o tipo ou o dado, nao `any`)
- import ou caminho errado (confira `paths` e extensao ESM/CJS)
- dependencia ausente ou duplicada
- versao de Node incompativel
