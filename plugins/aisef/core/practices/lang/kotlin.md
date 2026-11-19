---
paths:
  - "**/*.kt"
  - "**/*.kts"
description: Praticas de Kotlin
source: ECC rules/kotlin (MIT), condensado
---

# Kotlin

- `val` por padrão; `data class` imutável para valores; `sealed` para estados.
- Sem `!!`; use os recursos de nulidade (`?.`, `?:`, `requireNotNull` com mensagem).
- Coroutines com escopo estruturado (`viewModelScope`, `lifecycleScope`, escopo injetado); nunca `GlobalScope`; `runBlocking` só em teste e `main`.
- Android: domínio sem dependência de Android; ViewModel sem referência a View/Context; Compose com estado elevado e `remember`.
- detekt/ktlint limpos; testes com kotest ou JUnit e `kotlinx-coroutines-test`.
