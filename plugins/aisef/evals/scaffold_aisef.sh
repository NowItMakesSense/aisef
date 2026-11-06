#!/usr/bin/env bash
# Fixture: projeto git com o AISEF iniciado e agentes ativos. Chamado pelo scaffold_script de cada caso.
set -e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
core="$here/../core"
py=""
for c in python3 python py; do p=$(command -v $c 2>/dev/null) || continue; case "$p" in *WindowsApps*) continue;; esac; py=$p; break; done
git init -q . && git config user.email eval@aisef && git config user.name eval
printf '# Loja\n\nAplicacao de exemplo. O cliente vai recieve um e-mail de confirmacao.\n' > README.md
mkdir -p src && printf 'def total(itens):\n    return sum(i["preco"] for i in itens)\n' > src/carrinho.py
git add -A && git commit -qm init
"$py" -I "$core/aisef_project.py" init --project . --project-id PRJ-EVAL --name loja >/dev/null
"$py" -I "$core/aisef_project.py" agents --project . --activate >/dev/null
