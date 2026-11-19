Voce faz o build PyTorch voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`python -c 'import torch; print(torch.__version__, torch.cuda.is_available())' ; testes do projeto`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- formato de tensor incompativel (imprima `shape` em cada passo)
- tensor em dispositivos diferentes
- gradiente nao calculado (`requires_grad`, `no_grad`)
- falta de memoria (lote menor, acumulacao de gradiente)
