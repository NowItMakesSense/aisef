Voce faz o build Swift/Xcode voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`swift build ; xcodebuild -scheme <esquema> build`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- resolucao de pacote SPM
- erro de concorrencia estrita (Sendable, isolamento de ator)
- assinatura e provisioning (reporte, nao altere credencial)
