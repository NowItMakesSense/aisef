#!/usr/bin/env python3
"""AISEF design check: o codigo de UI respeita a autoridade de design do projeto (.aisef/design/tokens.json)?

    python -I design_check.py validate --project .                     tokens.json valido no schema
    python -I design_check.py scan     --project . [--task T-010 | --paths "web/**" ...] [--json]
                                       cores (hex/rgb) e familias de fonte fora dos tokens = violacao
    python -I design_check.py shots    --url http://localhost:3000/rota --out .aisef/reports/shots/T-010
                                       [--widths 375,768,1440]   capturas em Chrome headless (evidencia visual)

Deterministico, sem modelo: e o criterio de aceite "nenhum valor fora dos tokens" das fatias de UI. Saida 1 quando
ha violacao (scan) ou tokens invalidos (validate). Somente stdlib (+ jsonschema no validate).
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "design-tokens.schema.v0.1.json")
UI_EXT = (".css", ".scss", ".sass", ".less", ".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".astro")
HEX_RE = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")
RGB_RE = re.compile(r"\brgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})")
FONT_RE = re.compile(r"font-family\s*:\s*([^;}\n]+)|fontFamily\s*:\s*[\"'`]([^\"'`]+)[\"'`]", re.I)
GENERIC_FONTS = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif",
                 "ui-monospace", "inherit", "initial", "unset", "-apple-system", "blinkmacsystemfont", "emoji",
                 "math", "segoe ui", "helvetica neue", "arial", "helvetica", "sans", "var"}
SKIP_DIRS = {".git", "node_modules", ".aisef", "dist", "build", ".next", ".venv", "venv", "__pycache__", "coverage"}


def tokens_path(project):
    return os.path.join(project, ".aisef", "design", "tokens.json")


def load_tokens(project):
    with open(tokens_path(project), encoding="utf-8") as fh:
        return json.load(fh)


def norm_hex(h):
    h = h.lower().lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    return h[:6]  # alfa nao muda a cor de marca


def allowed_colors(tokens):
    return {norm_hex(v) for v in tokens.get("colors", {}).values()}


def allowed_fonts(tokens):
    fams = set()
    for v in tokens.get("typography", {}).get("families", {}).values():
        fams |= {f.strip().strip("\"'").lower() for f in v.split(",")}
    return fams


def ui_files(project, patterns, ignore):
    out = []
    for dp, dn, fn in os.walk(project):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if not f.lower().endswith(UI_EXT):
                continue
            rel = os.path.relpath(os.path.join(dp, f), project).replace("\\", "/")
            if patterns and not any(fnmatch.fnmatch(rel, p) for p in patterns):
                continue
            if any(fnmatch.fnmatch(rel, p) for p in ignore):
                continue
            out.append(rel)
    return sorted(out)


def scan(project, patterns=None, tokens=None):
    tokens = tokens or load_tokens(project)
    colors, fonts = allowed_colors(tokens), allowed_fonts(tokens)
    found = []
    for rel in ui_files(project, patterns or [], tokens.get("ignore_paths", [])):
        try:
            with open(os.path.join(project, rel), encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            for m in HEX_RE.finditer(line):
                if norm_hex(m.group(0)) not in colors:
                    found.append({"file": rel, "line": n, "kind": "color", "value": m.group(0)})
            for m in RGB_RE.finditer(line):
                hx = "%02x%02x%02x" % tuple(min(255, int(x)) for x in m.groups())
                if hx not in colors:
                    found.append({"file": rel, "line": n, "kind": "color", "value": m.group(0) + ")"})
            for m in FONT_RE.finditer(line):
                for fam in (m.group(1) or m.group(2) or "").split(","):
                    name = fam.strip().strip("\"'`").lower()
                    if name and not name.startswith("var(") and name not in fonts and name not in GENERIC_FONTS:
                        found.append({"file": rel, "line": n, "kind": "font", "value": fam.strip()})
    return found


def task_patterns(project, task_id):
    with open(os.path.join(project, ".aisef", "contracts", "tasks", task_id + ".json"), encoding="utf-8") as fh:
        return json.load(fh).get("scope", {}).get("paths_allowed", [])


def validate_tokens(project):
    sys.path.insert(0, HERE)
    import aisef_project as ap
    try:
        doc = load_tokens(project)
    except FileNotFoundError:
        return ["%s nao existe" % tokens_path(project)]
    except ValueError as exc:
        return ["tokens.json nao e JSON valido: %s" % exc]
    return ap.validate(doc, os.path.basename(SCHEMA))


def find_chrome():
    return (shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
            or shutil.which("chrome") or shutil.which("msedge") or next((p for p in (
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") if os.path.exists(p)), None))


def shots(url, out, widths):
    chrome = os.environ.get("CHROME_PATH") or find_chrome()
    if not chrome:
        raise SystemExit("Chrome/Edge nao encontrado (defina CHROME_PATH)")
    os.makedirs(out, exist_ok=True)
    made = []
    for w in widths:
        path = os.path.abspath(os.path.join(out, "w%d.png" % w))
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                        "--window-size=%d,%d" % (w, max(800, int(w * 1.6))), "--screenshot=" + path, url],
                       capture_output=True, timeout=90)
        if os.path.exists(path):
            made.append(path)
    return made


def main(argv=None):
    ap_ = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap_.add_argument("command", choices=["validate", "scan", "shots"])
    ap_.add_argument("--project", default=".")
    ap_.add_argument("--task")
    ap_.add_argument("--paths", nargs="*", default=[])
    ap_.add_argument("--json", action="store_true")
    ap_.add_argument("--url")
    ap_.add_argument("--out")
    ap_.add_argument("--widths", default="375,768,1440")
    a = ap_.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.command == "validate":
        problems = validate_tokens(project)
        print("tokens.json valido" if not problems else "tokens.json invalido:\n - " + "\n - ".join(problems))
        return 1 if problems else 0
    if a.command == "shots":
        if not (a.url and a.out):
            ap_.error("--url e --out sao obrigatorios")
        made = shots(a.url, a.out, [int(x) for x in a.widths.split(",") if x.strip()])
        print("\n".join(made) if made else "nenhuma captura gerada")
        return 0 if made else 1
    patterns = list(a.paths) + (task_patterns(project, a.task) if a.task else [])
    found = scan(project, patterns)
    if a.json:
        print(json.dumps({"violations": found, "count": len(found)}, ensure_ascii=False, indent=2))
    else:
        for v in found:
            print("%s:%d %s fora dos tokens: %s" % (v["file"], v["line"], "cor" if v["kind"] == "color" else "fonte", v["value"]))
        print("%d violacao(oes) de design" % len(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
