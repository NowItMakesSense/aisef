---
paths:
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.vue"
  - "**/*.svelte"
  - "**/*.html"
  - "**/*.css"
  - "**/*.scss"
description: Praticas de Web (frontend)
source: ECC rules/web (MIT), condensado
---

# Web (frontend)

- **Autoridade de design do projeto manda:** tipografia, cores, espaçamento e componentes vêm de `.aisef/design/tokens.json` e `DESIGN.md`. Estas regras não mudam o visual.
- Acessibilidade WCAG 2.2 AA: HTML semântico, rótulo em todo campo, foco visível, navegação por teclado, contraste mínimo, `prefers-reduced-motion`.
- Estados de carregamento, vazio e erro em toda tela que busca dados.
- Desempenho: imagens com tamanho e formato modernos, carregamento sob demanda de rotas pesadas, sem dependência gigante para pouca coisa; acompanhe Core Web Vitals.
- Segurança: nunca renderize HTML do usuário sem sanitizar; CSP quando possível; nada sensível em `localStorage`.
- Estado: o mínimo possível no global; derive em vez de duplicar; dados do servidor com a biblioteca de cache do projeto.
