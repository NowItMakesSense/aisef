#!/usr/bin/env sh
# Lancador dos hooks do AISEF: escolhe um Python que funcione (no Windows, "python3" pode ser o
# atalho da Microsoft Store, que existe no PATH mas nao executa). AISEF_PYTHON tem prioridade.
# Uso: run.sh <script.py> [pre|post]
script="$1"; phase="${2:-post}"
# projeto sem AISEF: nada a fazer (o plugin instalado nao interfere em outros projetos)
[ -f "${CLAUDE_PROJECT_DIR:-.}/.aisef/config.json" ] || exit 0
for py in "$AISEF_PYTHON" python3 python py; do
  [ -n "$py" ] || continue
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "" >/dev/null 2>&1; then
    exec "$py" -I "$(dirname "$0")/$script"
  fi
done
if [ "$phase" = "pre" ]; then
  # sem Python nao ha como avaliar a politica: falha fechada
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"AISEF: nenhum Python encontrado para o Execution Gateway (defina AISEF_PYTHON)"}}'
  exit 0
fi
echo "AISEF: nenhum Python encontrado; evento de auditoria nao registrado" >&2
exit 1
