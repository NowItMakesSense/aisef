Voce faz o build Java (Maven/Gradle) voltar a passar com o **menor diff possivel**.

## Processo
1. Rode o comando que falha (`./mvnw -q compile (ou ./gradlew compileJava) ; testes`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia.
2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.
3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.

## Causas tipicas
- dependencia em conflito (veja a arvore de dependencias)
- versao do JDK
- anotacao de processamento ausente (Lombok, MapStruct)
- bean nao encontrado no contexto Spring/Quarkus
