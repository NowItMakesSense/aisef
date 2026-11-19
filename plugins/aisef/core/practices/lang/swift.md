---
paths:
  - "**/*.swift"
description: Praticas de Swift
source: ECC rules/swift (MIT), condensado
---

# Swift

- `struct` e `enum` por padrão; `class` só quando identidade ou herança são necessárias.
- Sem force unwrap e `try!` em produção; `guard let` para sair cedo.
- Concorrência moderna: `async/await`, `actor` para estado compartilhado, `@MainActor` para UI, tipos `Sendable` entre fronteiras.
- `[weak self]` em closures guardadas pelo próprio objeto; cuidado com ciclos de referência.
- Credenciais no Keychain; nada sensível em `UserDefaults`.
- Protocolos pequenos para injeção de dependência e testes; XCTest ou Swift Testing.
