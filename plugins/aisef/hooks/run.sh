#!/usr/bin/env sh
# Lancador dos hooks do AISEF. Roda em toda chamada de ferramenta, entao precisa ser barato:
# - projeto sem .aisef/config.json: sai na hora (o plugin nao interfere em outros projetos);
# - AISEF_PYTHON, se definido, e usado direto (o mais rapido);
# - senao, o primeiro python3/python/py do PATH, pulando o atalho da Microsoft Store (WindowsApps),
#   que existe no PATH mas nao executa. Nenhum interpretador e executado "so para testar".
# hooks.json carrega este arquivo com "." (sem abrir outro shell; no Windows isso poupa ~80 ms) e passa
# o script e a fase por variaveis, que funcionam em qualquer sh POSIX:
#   AISEF_HOOKS=<dir> AISEF_SCRIPT=gateway.py AISEF_PHASE=pre . <dir>/run.sh
# Tambem funciona executado direto: sh run.sh <script.py> [pre|post]
script="${AISEF_SCRIPT:-$1}"; phase="${AISEF_PHASE:-${2:-post}}"
dir="${AISEF_HOOKS:-$(dirname "$0")}"
[ -f "${CLAUDE_PROJECT_DIR:-.}/.aisef/config.json" ] || exit 0
if [ -n "$AISEF_PYTHON" ]; then
  exec "$AISEF_PYTHON" -I "$dir/$script"
fi
for py in python3 python py; do
  path=$(command -v "$py" 2>/dev/null) || continue
  case "$path" in *WindowsApps*) continue ;; esac
  exec "$path" -I "$dir/$script"
done
if [ "$phase" = "pre" ]; then
  # sem Python nao ha como avaliar a politica: falha fechada
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"AISEF: nenhum Python encontrado para o Execution Gateway (defina AISEF_PYTHON)"}}'
  exit 0
fi
echo "AISEF: nenhum Python encontrado; evento de auditoria nao registrado" >&2
exit 1
