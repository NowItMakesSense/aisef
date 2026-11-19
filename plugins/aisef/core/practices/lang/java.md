---
paths:
  - "**/*.java"
description: Praticas de Java
source: ECC rules/java (MIT), condensado
---

# Java

- Injeção por construtor; campos `final`; records para DTOs e objetos de valor.
- Entidade JPA nunca exposta na API; DTO e mapeamento na fronteira; consultas com parâmetro (nada de concatenar JPQL/SQL).
- Evite N+1: `JOIN FETCH` ou entity graph; `FetchType.LAZY` por padrão.
- `@Transactional` em métodos públicos do serviço (proxy não intercepta chamada interna nem método privado).
- `Optional` como retorno quando pode faltar, nunca como campo ou parâmetro; coleção vazia em vez de `null`.
- try-with-resources para todo recurso; exceção específica; não engula `Exception`.
- Testes: JUnit 5, AssertJ, Testcontainers para integração com banco real.
