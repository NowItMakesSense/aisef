#!/usr/bin/env bash
# Projeto AISEF com discovery pronto: a aisef-tooling precisa dele para montar os termos de busca.
set -e
bash "$(dirname "${BASH_SOURCE[0]}")/../scaffold_aisef.sh"
cat > .aisef/discovery.md <<'MD'
# Discovery - Loja

## Visao
Loja online pequena (confirmado pelo usuario).

## Requisitos
- RF-1 Pagamento com cartao via Stripe (user_stated).
- RF-2 Testes de ponta a ponta do checkout com Playwright (user_stated).

## Arquitetura atual ou proposta
Python (src/carrinho.py, encontrado). Banco: PostgreSQL (user_stated).

## Desconhecidos
- Hospedagem.
MD
