---
paths:
  - "**/*.cpp"
  - "**/*.cc"
  - "**/*.cxx"
  - "**/*.hpp"
  - "**/*.hh"
  - "**/*.h"
description: Praticas de C++
source: ECC rules/cpp (MIT), condensado
---

# C++

- C++ moderno (17/20) e C++ Core Guidelines; `clang-format` e `clang-tidy` limpos.
- RAII para todo recurso; `unique_ptr`/`make_unique`; `shared_ptr` só com posse compartilhada real; nada de `new`/`delete` manual.
- Sem `strcpy`/`sprintf`/`gets`; `std::string`, `std::span`, `std::array` com checagem de limites.
- `const` e `constexpr` por padrão; casts nomeados; destrutor virtual em classe base polimórfica.
- Concorrência com `std::scoped_lock`; testes com sanitizers (ASan, UBSan, TSan) no CI.
