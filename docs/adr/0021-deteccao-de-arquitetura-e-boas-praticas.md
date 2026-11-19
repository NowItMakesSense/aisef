# ADR 0021: Detecção de arquitetura e boas práticas

- **Status:** aceito
- **Data:** 2026-11-19

## Contexto

O usuário pediu que o AISEF detecte se o projeto usa DDD, Clean Architecture e outros estilos, e recomende melhorias. Pediu também boas práticas melhores. Até a 0.11, a descoberta era só texto: nada detectava stack nem estilo, e Clean Code, Clean Architecture, DDD e SOLID não estavam escritos em lugar nenhum. O ECC tem detecção de stack (`project-detect.js`, `project-stack-mappings.json`) e regras por linguagem. Não tem DDD, CQRS nem detecção de estilo.

## Decisão

- **`core/aisef_detect.py`** (stdlib, sem modelo nem rede) grava `.aisef/architecture.json`:
  - stacks;
  - estilos com confiança e evidência;
  - camadas;
  - violações da regra de dependência lidas dos imports;
  - práticas aplicáveis;
  - recomendações com motivo, impacto e esforço.
- **É heurística.** Nome de pasta não prova estilo. A skill `aisef-discovery` manda confirmar no código. **Adotar um estilo é decisão do usuário:** pedido `architecture_decision` aprovado, e então `detect --adopt`. As regras `ARCH-*` conferem isso.
- **O estilo adotado tem efeito:**
  - ativa os papéis por arquitetura;
  - faz o `architecture-reviewer` revisar toda tarefa;
  - escolhe as práticas instaladas;
  - entra no pacote de contexto.
- **Práticas em `core/practices/`:** `common`, `architecture` e `lang`.
  - Cada prática de arquitetura diz **quando não usar**. O AISEF recomenda sem dogma: DDD tático e CQRS só onde o domínio pede.
  - `practices --apply` instala em `.claude/rules/aisef/`. As regras de linguagem usam `paths:` para carregar só nos arquivos certos. Arquivo mudado no projeto não é sobrescrito.

## Consequências

- O AISEF passa a ter opinião explícita sobre arquitetura, mas não muda nada sozinho.
- **Falso positivo de estilo** é o risco principal, mitigado pela confirmação no código e pela decisão do usuário. Medir a precisão em repositórios reais está na lista de avaliação.
- A regra de dependência por regex de import não substitui uma ferramenta de arquitetura da stack (ArchUnit, import-linter, dependency-cruiser), que a prática de monólito modular recomenda para o CI.
