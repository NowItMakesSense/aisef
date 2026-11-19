---
paths:
  - "**/*.py"
  - "**/*.pyi"
description: Praticas de Python
source: ECC rules/python (MIT), condensado
---

# Python

- Siga PEP 8 e o formatador/linter do projeto (ruff, black); type hints em toda função pública e `mypy`/`pyright` no CI quando o projeto tipa.
- Nada de argumento padrão mutável; `with` para todo recurso; `pathlib` para caminhos; `datetime` sempre com fuso.
- Exceções específicas (`except ValueError`), nunca `except:` vazio; `raise ... from err` para manter a causa.
- `subprocess` com lista de argumentos (sem `shell=True` com entrada externa); SQL parametrizado; `yaml.safe_load`; nunca `pickle` de dado externo.
- Em `async def`, nada bloqueante (requests, `time.sleep`, driver síncrono): use as versões assíncronas ou `run_in_executor`.
- `dataclass(frozen=True)` ou Pydantic para objetos de valor; `Enum` em vez de strings mágicas.
- Testes com pytest: fixtures pequenas, `parametrize` para tabelas de casos, nada de rede real em teste de unidade.
- Dependências declaradas no manifest com versão mínima; lockfile commitado em aplicação (não em biblioteca).
