---
paths:
  - "**/*.go"
description: Praticas de Go
source: ECC rules/golang (MIT), condensado
---

# Go

- `gofmt`/`goimports`, `go vet` e `staticcheck` limpos; `go test -race` no CI.
- Todo erro tratado; contexto com `fmt.Errorf("...: %w", err)`; comparação com `errors.Is`/`errors.As`; `panic` só para erro de programação.
- `context.Context` como primeiro parâmetro em toda operação de I/O, propagado e respeitado (cancelamento e prazo).
- Goroutine sempre com forma clara de terminar; canais com dono definido; `sync` ou canal para estado compartilhado, nunca nada.
- Interfaces pequenas, definidas por quem usa; aceite interfaces, devolva structs.
- Pacotes por domínio, não `utils`/`common`; `internal/` para o que não é API pública.
- Testes em tabela (`[]struct{...}`) e `t.Run`; `httptest` para HTTP.
