#!/usr/bin/env python3
"""Testes da E-01b: teste rodado depois de um heredoc grande tambem conta como evidencia de TDD.
O hook guarda 400 caracteres do comando; as invocacoes de teste vao em `test_runs` e o check as procura ali."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project as ap  # noqa: E402
import check_rules_4 as r4  # noqa: E402
import shell_test_runs as st  # noqa: E402

HOOK = os.path.join(os.path.dirname(HERE), "hooks", "audit_hook.py")
fails = total = 0


def check(name, cond, extra=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or extra is None else "  -> %s" % (extra,)))
    fails += not cond


BODY = "\n".join("it('caso %d', () => { expect(vitest_like(%d)).toBe(true); });" % (i, i) for i in range(40))
LONG = ("cd C:/repo && cat > packages/x/test/cv.test.ts <<'EOF'\nimport { it, expect } from 'vitest';\n" + BODY +
        "\nEOF\ncd packages/x && pnpm exec vitest run test/cv.test.ts 2>&1 | tail -20")

# ---------------------------------------------------------------- extrator
check("acha o teste rodado depois do heredoc", st.extract(LONG) == ["pnpm exec vitest run test/cv.test.ts 2>&1"], st.extract(LONG))
check("ignora o corpo do heredoc (o arquivo cita vitest, mas nao e comando)", all("expect" not in r for r in st.extract(LONG)))
check("varios executores em sequencia", st.extract("pytest -q tests && npm test; go test ./...") == ["pytest -q tests", "npm test", "go test ./..."])
check("comando sem teste: lista vazia", st.extract("git status && ls -la") == [])
check("heredoc sem aspas e com <<-", st.extract("cat <<-FIM\nvitest run nada\nFIM\njest --ci") == ["jest --ci"])

# ---------------------------------------------------------------- hook grava test_runs
proj = os.path.join(work, "p")
os.makedirs(proj)
ap.init(proj, "PRJ-T", "runs", "dev")
payload = {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "tool_input": {"command": LONG},
           "error": "Exit code 1\nFAIL test/cv.test.ts", "cwd": proj, "session_id": "s1"}
subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(payload), text=True, capture_output=True, cwd=proj,
               env=dict(os.environ), timeout=60)
import audit_chain  # noqa: E402
log = audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))
ev = [e for e in log if (e.get("data") or {}).get("tool") == "Bash"]
d = ev[-1]["data"] if ev else {}
check("hook: comando longo grava as invocacoes de teste em test_runs, com o resultado",
      d.get("test_runs") == ["pnpm exec vitest run test/cv.test.ts 2>&1"] and d.get("exit_code") == 1, d)
check("hook: o comando em si continua cortado em 400 caracteres", len(d.get("command", "")) == 400)

# ---------------------------------------------------------------- o check acha o vermelho
runs = r4.shell_runs(log)
hit, why = r4.match_run(runs, "red", {"command": "pnpm exec vitest run test/cv.test.ts", "at": ev[-1]["timestamp"]})
check("check: o vermelho declarado bate com o test_runs do log", hit is not None, why)
hit, why = r4.match_run(runs, "green", {"command": "pnpm exec vitest run test/cv.test.ts", "at": ev[-1]["timestamp"]})
check("check: e nao vale como verde (o log diz que falhou)", hit is None and "falhando" in (why or ""), why)

import shutil  # noqa: E402
shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
