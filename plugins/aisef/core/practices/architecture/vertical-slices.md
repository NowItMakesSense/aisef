---
description: Arquitetura por fatias verticais / feature-sliced
source: AISEF
---

# Fatias verticais (vertical slice architecture) e feature-sliced design

**Ideia:** organizar o código por **funcionalidade** (uma pasta por caso de uso ou feature com tudo que ela precisa: endpoint, handler, validação, acesso a dados, teste), em vez de por camada técnica.

- Acoplamento dentro da fatia é aceitável; entre fatias, mínimo. Compartilhe só o que é realmente comum (domínio, infraestrutura transversal).
- Combina com o fluxo de trabalho do AISEF (cada fatia vertical da spec vira uma pasta coesa).
- **Feature-sliced design (frontend):** camadas `app` → `pages` → `widgets` → `features` → `entities` → `shared`; uma camada só importa camadas abaixo dela; cada slice expõe uma API pública (`index`).

## Sinais de problema
Fatias que importam o interior umas das outras; lógica de domínio duplicada em várias fatias (extraia para o domínio); pasta `shared` virando depósito.

## Quando não usar
Domínio rico com muitas regras que atravessam features: o domínio precisa de um lugar próprio (combine fatias com um núcleo de domínio).
