Voce faz o build HarmonyOS (ArkTS/ArkUI) voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`hvigorw assembleHap (ou o build do projeto)`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- gerenciamento de estado V2 (`@ComponentV2`, `@Local`, `@Param`) misturado com V1
- API de ArkTS que nao existe na versao alvo
- permissao ausente no `module.json5`
