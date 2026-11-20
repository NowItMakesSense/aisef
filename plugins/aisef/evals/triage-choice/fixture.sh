#!/usr/bin/env bash
# Projeto do scaffold comum com o perfil solo (C-01): a triagem decide entre quick, lean e full.
set -e
bash "$(dirname "${BASH_SOURCE[0]}")/../scaffold_aisef.sh"
py=""
for c in python3 python py; do p=$(command -v $c 2>/dev/null) || continue; case "$p" in *WindowsApps*) continue;; esac; py=$p; break; done
"$py" -I - <<'PY'
import json
p = ".aisef/config.json"
cfg = json.load(open(p, encoding="utf-8"))
cfg["profile"] = "solo"
json.dump(cfg, open(p, "w", encoding="utf-8"), indent=2)
PY
