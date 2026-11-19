---
paths:
  - "**/*.cs"
  - "**/*.fs"
description: Praticas de C# / F# (.NET)
source: ECC rules/csharp e fsharp (MIT), condensado
---

# C# / F# (.NET)

- Nullable reference types ligado; avisos tratados como erro no CI.
- `async` até o fim: nada de `.Result`/`.Wait()`; `async void` só em handler de evento; `CancellationToken` propagado.
- `using`/`await using` para todo `IDisposable`; exceções específicas; nada de engolir `Exception`.
- EF Core: `AsNoTracking` em leitura, `Include` para evitar N+1, migrations revisadas; SQL cru só parametrizado.
- Injeção de dependência com tempo de vida correto (nada de serviço scoped dentro de singleton); options pattern para configuração.
- records para DTOs e objetos de valor; F#: uniões discriminadas e `Result` para erros esperados.
- Testes: xUnit/NUnit, FluentAssertions, WebApplicationFactory e Testcontainers para integração.
