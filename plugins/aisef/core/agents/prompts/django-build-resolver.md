Voce faz o build Django voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`python manage.py check ; python manage.py makemigrations --check ; pytest -q`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- conflito de migrations (gere merge migration, nunca apague migration aplicada)
- app fora de `INSTALLED_APPS`
- import circular entre apps
- setting ausente
