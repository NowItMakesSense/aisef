#!/usr/bin/env bash
set -e
bash "$(dirname "${BASH_SOURCE[0]}")/../scaffold_aisef.sh"
printf '# Discovery\n\n## Visao\nLoja com carrinho em src/carrinho.py (encontrado).\n\n## Testes\nSem testes ainda (encontrado).\n' > .aisef/discovery.md
