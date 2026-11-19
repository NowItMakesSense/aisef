Voce faz o build Rust voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`cargo check ; cargo clippy ; cargo build`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- erro do borrow checker (reestruture o escopo antes de clonar)
- lifetime ausente
- trait nao implementada
- feature de crate desligada
