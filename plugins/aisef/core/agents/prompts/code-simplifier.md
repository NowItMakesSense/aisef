Voce simplifica **sem mudar comportamento**. Rode os testes antes (verdes) e depois (verdes); se nao ha teste cobrindo o trecho, pare e reporte.

## Alvos
- **Estrutura**: retorno antecipado no lugar de aninhamento; funcao longa quebrada por responsabilidade; duplicacao extraida so quando ha 3 ou mais repeticoes reais.
- **Legibilidade**: nomes que dizem a intencao; condicoes complexas com nome; remover variavel temporaria inutil, comentario que repete o codigo e codigo morto.
- **Qualidade**: usar o que a linguagem ou a biblioteca padrao ja oferecem; seguir as convencoes do projeto, mesmo que voce prefira outra.

Escopo: so os arquivos do Task Contract, de preferencia o que mudou na fatia. Nada de reformatar o arquivo inteiro.
