---
paths:
  - "**/*.php"
description: Praticas de PHP
source: ECC rules/php (MIT), condensado
---

# PHP

- PSR-12; `declare(strict_types=1);` e tipos em parâmetros, retornos e propriedades.
- Laravel: validação em Form Request, autorização em Policy/Gate, `$fillable` explícito, `with()` contra N+1, transação em operações múltiplas.
- Nada de `DB::raw`/SQL com interpolação de entrada; `{{ }}` (escapado) nas views, `{!! !!}` só com HTML confiável.
- Controller fino; regra de negócio em serviços ou ações; `env()` só nos arquivos de configuração.
- PHPStan/Psalm no nível acordado; testes com PHPUnit ou Pest.
