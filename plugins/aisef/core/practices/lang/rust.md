---
paths:
  - "**/*.rs"
description: Praticas de Rust
source: ECC rules/rust (MIT), condensado
---

# Rust

- `cargo fmt` e `cargo clippy -- -D warnings` limpos.
- `Result` com erro tipado (`thiserror` em biblioteca, `anyhow` em aplicação); `?` para propagar; `unwrap`/`expect` só em teste ou com invariante comentada.
- `unsafe` mínimo, isolado e com comentário `// SAFETY:` provando a invariante.
- Prefira empréstimo a `clone`; `&str`/`&[T]` em parâmetros; `Arc<Mutex<_>>` só quando a posse compartilhada é real.
- Não segure lock através de `.await`; use o runtime assíncrono do projeto de forma consistente.
- Tipos novos (`struct Email(String)`) para invariantes; `#[must_use]` em resultados importantes.
