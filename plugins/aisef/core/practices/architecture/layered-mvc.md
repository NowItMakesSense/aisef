---
description: Camadas simples e MVC, com regra de negocio fora dos controllers
source: AISEF
---

# Camadas / MVC

Boa escolha para aplicações de complexidade moderada e para frameworks que já impõem MVC (Rails, Laravel, Django, Spring MVC, ASP.NET MVC).

- **Controller fino:** recebe a requisição, valida o formato, chama **um** serviço (ou caso de uso) e devolve a resposta. Sem regra de negócio.
- **Serviço / caso de uso:** onde mora a regra de negócio e a transação.
- **Modelo / repositório:** acesso a dados. Modelo do ORM pode ter comportamento simples do próprio dado, mas regra que envolve vários modelos vai para o serviço.
- **View / serializer:** formato de saída; sem consulta ao banco nem regra.
- Dependência de cima para baixo: controller → serviço → repositório. Nunca o contrário.

## Sinais de problema
*Fat controller* (centenas de linhas, regra e consulta misturadas); regra de negócio em callback do ORM ou em signal; view fazendo consulta (N+1 escondido); "serviço" que só repassa para o repositório.

## Quando evoluir
Quando a regra de negócio cresce e começa a se repetir entre serviços, extraia um domínio explícito (`clean-architecture`) ou módulos por contexto (`modular-monolith`).
