---
description: Clean Architecture / Onion - regra de dependencia e camadas
source: AISEF
---

# Clean Architecture (e Onion)

**Ideia:** o núcleo (regras de negócio) não conhece detalhes (banco, framework, UI, filas). As dependências apontam sempre **para dentro**.

## Camadas (de dentro para fora)
1. **Domínio** — entidades, objetos de valor, regras e invariantes; interfaces que o domínio precisa (repositórios, relógio, gerador de id). Sem framework, ORM, HTTP nem I/O.
2. **Aplicação** — casos de uso: orquestram o domínio para cumprir uma intenção do usuário, controlam a transação e chamam portas. Não decidem regra de negócio.
3. **Infraestrutura** — implementações das portas: ORM, clientes HTTP, filas, arquivos, e-mail.
4. **Apresentação** — controllers, handlers, CLI, telas: traduzem entrada e saída e chamam casos de uso.

## Regras
- **Regra de dependência:** domínio não importa aplicação, infraestrutura, apresentação nem framework; aplicação não importa infraestrutura nem apresentação. O `aisef_detect.py deps` e o `architecture-reviewer` conferem isso.
- DTOs na fronteira; entidade de domínio não vira resposta de API nem entidade do ORM (mapeie).
- Um caso de uso por intenção (`CriarPedido`, `CancelarPedido`), com entrada e saída explícitas.
- Composição (injeção de dependência) só na raiz da aplicação (`main`, container, `Program.cs`).

## Sinais de problema
Regra de negócio no controller ou no repositório; domínio com anotação de ORM ou importando o framework web; caso de uso chamando outro caso de uso em cadeia; "serviço" com centenas de linhas que faz tudo.

## Quando não usar
CRUD sem regra de negócio, protótipo ou script: as camadas viram cerimônia. Prefira camadas simples (`layered-mvc`) ou fatias verticais, e evolua quando a regra de negócio crescer.

## Migração incremental
Comece pelo módulo de maior regra de negócio: extraia o domínio puro com testes, defina as portas que ele usa, mova a persistência para adaptadores. Uma fatia por vez; o resto do sistema segue funcionando.
