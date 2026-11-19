---
description: SOLID e Clean Code aplicados com juizo
source: AISEF
---

# SOLID e Clean Code

- **S — responsabilidade única:** um módulo tem um motivo para mudar (um ator do negócio). Classe que muda por pedido do financeiro e do marketing está fazendo duas coisas.
- **O — aberto/fechado:** novos casos entram por extensão (estratégia, polimorfismo, tabela) quando a variação é real e recorrente; não crie pontos de extensão especulativos.
- **L — substituição de Liskov:** subtipo honra o contrato do tipo base (pré-condições não mais fortes, pós-condições não mais fracas). Se precisa de `if (x is Subtipo)`, a hierarquia está errada.
- **I — segregação de interfaces:** interfaces pequenas, do ponto de vista de quem usa; ninguém depende de método que não chama.
- **D — inversão de dependência:** regra de negócio depende de abstrações que ela define; detalhes (banco, framework, HTTP) implementam essas abstrações.

Clean Code, no dia a dia:
- funções pequenas que fazem uma coisa, no mesmo nível de abstração; sem argumentos booleanos que mudam o comportamento (divida em duas funções);
- sem efeitos colaterais escondidos; comando ou consulta, não os dois;
- erros por exceção ou tipo de resultado, não por código mágico de retorno;
- a regra do escoteiro: deixe o código que você tocou um pouco melhor — dentro do escopo da tarefa.

**Quando não forçar:** script de uso único, protótipo descartável e código gerado não precisam de camadas nem de interfaces.
