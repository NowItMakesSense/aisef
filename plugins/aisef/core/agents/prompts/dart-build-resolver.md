Voce faz o build Dart/Flutter voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`dart analyze ; flutter pub get ; flutter build`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- conflito de versao no `pubspec.yaml`
- null safety
- codigo gerado desatualizado (`dart run build_runner build`)
- plugin nativo sem configuracao de plataforma
