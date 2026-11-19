---
description: DDD tatico - agregados, entidades, objetos de valor, eventos, repositorios
source: AISEF
---

# DDD tático

Use quando o **domínio é rico**: regras que mudam com o negócio, invariantes que atravessam vários dados, linguagem própria dos especialistas.

## Blocos
- **Entidade:** identidade que persiste no tempo (`Pedido#123`); comportamento junto do dado (`pedido.cancelar()`), não setters.
- **Objeto de valor:** definido pelos atributos, **imutável**, comparado por valor, valida-se na criação (`Dinheiro`, `Email`, `Periodo`). Troque primitivos por objetos de valor onde há regra.
- **Agregado:** grupo de objetos com **uma raiz** que garante as invariantes. Regras:
  - alteração só pela raiz; ninguém de fora segura referência a objeto interno;
  - **uma transação altera um agregado**; consistência entre agregados é eventual (eventos);
  - outros agregados são referenciados **por id**, nunca por objeto;
  - agregados pequenos — desenhe pela invariante, não pelo diagrama de entidades.
- **Evento de domínio:** fato que aconteceu, nome no passado (`PedidoPago`), imutável; dispara reações em outros agregados ou contextos.
- **Repositório:** um por agregado, interface no domínio, coleção do agregado inteiro (sem métodos genéricos de consulta por campo).
- **Serviço de domínio:** regra que não pertence a uma entidade só (ex.: transferência entre contas). Sem estado.
- **Fábrica:** quando criar o agregado válido é complexo.

## Sinais de problema
Modelo anêmico (entidades só com getters/setters e a regra num "service"); agregado gigante que trava concorrência; referências diretas entre agregados; repositório genérico `Repository<T>` com `findBy*` para tudo.

## Quando não usar
CRUD, relatórios, integrações simples, domínio estável e pobre. DDD tático aí é custo sem retorno — o próprio Evans recomenda aplicá-lo só no **core domain**.
