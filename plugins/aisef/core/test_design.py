#!/usr/bin/env python3
"""Testes da autoridade de design (0.6.1): schema dos tokens, design_check (scan), regras DESIGN-* do check,
pacote de contexto com o design e criterio automatico nas fatias de UI."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_context as ctx  # noqa: E402
import aisef_new  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_project as cp  # noqa: E402
import design_check as dc  # noqa: E402

POL = os.path.join(HERE, "permission-policy.v0.1.json")
DEF = os.path.join(HERE, "orchestration-defaults.v0.1.json")
fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or detail is None else "  " + str(detail)[:300]))
    fails += not cond


TOKENS = {
    "schema_version": "0.1.0", "version": 1, "status": "proposed", "kind": "product_app",
    "typography": {"families": {"body": "Inter, sans-serif", "mono": "JetBrains Mono"},
                   "scale": {"sm": "0.875rem", "base": "1rem", "lg": "1.25rem"}},
    "colors": {"ink": "#111827", "paper": "#ffffff", "brand": "#0f766e"},
    "spacing": {"1": "4px", "2": "8px", "4": "16px"},
    "motion": {"level": "subtle", "scroll_linked": False},
    "components": ["Button", "TextField"], "rules": ["Um so acento de cor por tela"],
    "sources": ["ui-ux-pro-max", "impeccable"],
}

proj = os.path.join(work, "p")
os.makedirs(os.path.join(proj, "web"))
ap.init(proj, "PRJ-D", "design", "dev")
ap.activate_agents(proj)
os.makedirs(os.path.join(proj, ".aisef", "design"))
tok_path = os.path.join(proj, ".aisef", "design", "tokens.json")
ap.write_json(tok_path, TOKENS)

check("tokens validos no schema", dc.validate_tokens(proj) == [])
bad = dict(TOKENS, colors={"ink": "azul"})
ap.write_json(tok_path, bad)
check("cor que nao e hex e recusada pelo schema", dc.validate_tokens(proj) != [])
ap.write_json(tok_path, TOKENS)

with open(os.path.join(proj, "web", "ok.css"), "w", encoding="utf-8") as fh:
    fh.write(".a { color: #111827; background: #FFF; font-family: Inter, sans-serif; }\n.b { color: rgb(15, 118, 110); }\n")
with open(os.path.join(proj, "web", "bad.tsx"), "w", encoding="utf-8") as fh:
    fh.write('const s = { color: "#ff00ff", fontFamily: "Comic Sans MS" };\nconst t = "rgba(1, 2, 3, 0.5)";\n')
found = dc.scan(proj)
check("scan: valores dos tokens (hex curto, maiusculo e rgb) nao sao violacao",
      not [v for v in found if v["file"] == "web/ok.css"], found)
check("scan: cor e fonte fora dos tokens sao violacoes com arquivo e linha",
      {(v["kind"], v["value"]) for v in found if v["file"] == "web/bad.tsx"}
      == {("color", "#ff00ff"), ("font", "Comic Sans MS"), ("color", "rgba(1, 2, 3)")}, found)
check("scan: limitado aos paths da tarefa", dc.scan(proj, ["web/ok.css"]) == [])
check("CLI scan sai com 1 quando ha violacao", dc.main(["scan", "--project", proj]) == 1)

# ---- check: DESIGN-*
def codes():
    return {f["rule"] for f in cp.check(os.path.join(proj, ".aisef"), HERE, POL, DEF).findings}


ap.write_json(tok_path, dict(TOKENS, status="approved"))
check("tokens 'approved' sem decisao arquitetural aprovada -> DESIGN-UNAPPROVED", "DESIGN-UNAPPROVED" in codes())
ap.write_json(tok_path, dict(TOKENS, colors={"x": "nope"}))
check("tokens fora do schema -> DESIGN-SCHEMA", "DESIGN-SCHEMA" in codes())
ap.write_json(tok_path, TOKENS)

# ---- gerador: fatia de UI ganha criterio de design; pacote leva o design
brief = json.loads(json.dumps(aisef_new.EXAMPLES["feature"]))
aisef_new.cmd_feature(proj, brief)
t11 = json.load(open(os.path.join(proj, ".aisef", "contracts", "tasks", "T-011.json"), encoding="utf-8"))
t10 = json.load(open(os.path.join(proj, ".aisef", "contracts", "tasks", "T-010.json"), encoding="utf-8"))
crit = {c["id"]: c for c in t11["acceptance_criteria"]}
check("fatia que toca UI ganha o criterio de design com o comando do design_check",
      "AC-T-011-DESIGN" in crit and "design_check.py scan" in crit["AC-T-011-DESIGN"]["verification"]["command"])
check("fatia sem UI nao ganha criterio de design", not any(c["id"].endswith("-DESIGN") for c in t10["acceptance_criteria"]))
check("tarefa de UI aberta sem design aprovado -> aviso DESIGN-MISSING", "DESIGN-MISSING" in codes())
pack = ctx.build_pack(proj, "T-011")
d = pack["mandatory"]["design"]
check("pacote da fatia de UI traz a autoridade de design (fontes, cores, regras e o comando de conferencia)",
      d and d["families"]["body"].startswith("Inter") and "brand" in d["colors"] and "design_check.py" in d["check"]
      and "Autoridade de design" in ctx.render_pack(pack), d)
check("pacote avisa quando o design ainda nao foi aprovado", any("nao aprovada" in w for w in pack["warnings"]))
check("pacote de fatia sem UI nao traz design", ctx.build_pack(proj, "T-010")["mandatory"]["design"] is None)

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
