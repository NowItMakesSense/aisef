Voce faz o build Go voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`go build ./... ; go vet ./... ; go mod tidy`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- import nao usado ou ausente
- `go.mod` desatualizado (`go mod tidy`)
- interface nao satisfeita
- ciclo de import (extraia o tipo comum)
