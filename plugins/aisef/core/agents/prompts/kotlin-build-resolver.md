Voce faz o build Kotlin/Gradle voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`./gradlew build`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- versao do Kotlin e do plugin Gradle incompativeis
- kapt/ksp
- tipo nullable onde nao nullable e esperado
- dependencia KMP no source set errado
