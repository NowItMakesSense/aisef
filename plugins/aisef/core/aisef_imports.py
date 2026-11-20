#!/usr/bin/env python3
"""AISEF imports (0.13, G-06): extrai imports do codigo e resolve cada um para o arquivo do repositorio. Somente stdlib.

Usado pelo radar de arquitetura (aisef_detect: regra de dependencia e fronteira entre modulos) e pelo grafo nativo
(aisef_graph.build_native), que existe para o pacote de contexto ter raio de impacto mesmo sem o Graphify.

Resolucao por heuristica, sem rodar compilador:
- relativo (./x, ../x, .mod em Python, require_relative): resolvido contra a pasta do arquivo;
- nome qualificado (pkg.mod, com.x.Foo, App\\Models\\User, crate::a::b): casado pelo sufixo do caminho;
- namespace (C#) e pacote (Go, import com * em Java): casado com uma pasta, ligando aos arquivos dela;
- biblioteca externa (react, os, System.*) nao casa com nada e fica de fora.
Ambiguo demais (mais de MAX_TARGETS candidatos) e descartado, para nao inventar dependencia.
"""
import os
import re

IMPORT_RES = {
    ".py": [re.compile(r"^\s*from\s+([\w.]+)\s+import", re.M), re.compile(r"^\s*import\s+([\w.]+)", re.M)],
    ".ts": [re.compile(r"""(?:import|export)\s[^'"]*?from\s+['"]([^'"]+)['"]"""), re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
            re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.M)],
    ".java": [re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+(?:\.\*)?)", re.M)],
    ".cs": [re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", re.M)],
    ".go": [re.compile(r"""^\s*(?:import\s+)?(?:\w+\s+)?"([^"]+)"\s*$""", re.M)],
    ".php": [re.compile(r"^\s*use\s+([\w\\]+)", re.M)],
    ".rb": [re.compile(r"""^\s*require(?:_relative)?\s+['"]([^'"]+)['"]""", re.M)],
    ".dart": [re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.M)],
    ".rs": [re.compile(r"^\s*use\s+([\w:]+)", re.M)],
}
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
for _e in JS_EXT[1:]:
    IMPORT_RES[_e] = IMPORT_RES[".ts"]
IMPORT_RES[".kt"] = IMPORT_RES[".java"]
IMPORT_RES[".scala"] = IMPORT_RES[".java"]

# familia de extensoes que um import pode alcancar, por extensao do arquivo que importa
FAMILY = {".py": (".py",), ".java": (".java", ".kt", ".scala"), ".kt": (".kt", ".java"), ".scala": (".scala", ".java"),
          ".cs": (".cs",), ".go": (".go",), ".php": (".php",), ".rb": (".rb",), ".dart": (".dart",), ".rs": (".rs",)}
for _e in JS_EXT:
    FAMILY[_e] = JS_EXT
JS_ALIASES = ("@/", "~/", "#/", "src/")
MAX_TARGETS = 3        # mais candidatos que isso para um import por arquivo = ambiguo, descarta
MAX_DIR_TARGETS = 25   # namespace/pacote ligado a uma pasta: no maximo tantos arquivos dela
MAX_SUFFIX = 8         # profundidade dos sufixos indexados


def imports_in(text, ext):
    """[(import, linha)] do texto, pela extensao do arquivo."""
    out = []
    for rx in IMPORT_RES.get(ext, ()):
        for m in rx.finditer(text):
            out.append((m.group(1), text.count("\n", 0, m.start()) + 1))
    return out


class Resolver:
    """Indices por sufixo de caminho (sem extensao) e por pasta, montados uma vez para o repositorio."""

    def __init__(self, files):
        self.files = set(files)
        self.by_suffix = {}   # "a/b/c" (sem extensao) -> [arquivos]
        self.by_dir = {}      # "src/x" -> [arquivos de codigo direto nela]
        self.dir_suffix = {}  # "x/y" -> [pastas] (Go, Java *)
        self.dir_dotted = {}  # "Loja.Pedidos.Domain" -> [pastas] (C#)
        for f in files:
            stem, ext = os.path.splitext(f)
            if ext not in IMPORT_RES:
                continue
            segs = stem.split("/")
            for k in range(1, min(len(segs), MAX_SUFFIX) + 1):
                self.by_suffix.setdefault("/".join(segs[-k:]), []).append(f)
            d = os.path.dirname(f)
            self.by_dir.setdefault(d, []).append(f)
        for d in self.by_dir:
            segs = d.split("/") if d else []
            for k in range(1, min(len(segs), MAX_SUFFIX) + 1):
                self.dir_suffix.setdefault("/".join(segs[-k:]), []).append(d)
                self.dir_dotted.setdefault(".".join(segs[-k:]), []).append(d)

    def _pick(self, cands, ext):
        fam = FAMILY.get(ext, (ext,))
        found = sorted({c for c in cands if os.path.splitext(c)[1] in fam})
        return found if 0 < len(found) <= MAX_TARGETS else []

    def _suffix(self, path, ext):
        return self._pick(self.by_suffix.get(path.strip("/"), ()), ext)

    def _exact(self, stem, ext, index_names=()):
        """Arquivo exato a partir de um caminho sem extensao (ou com), tentando a familia e os arquivos indice."""
        stem = os.path.normpath(stem).replace(os.sep, "/")
        if stem.startswith(".."):
            return []
        if stem in self.files:
            return [stem]
        for e in FAMILY.get(ext, (ext,)):
            if stem + e in self.files:
                return [stem + e]
        prefix = "" if stem in ("", ".") else stem + "/"
        for name in index_names:
            for e in FAMILY.get(ext, (ext,)):
                p = prefix + name + e
                if p in self.files:
                    return [p]
        return []

    def _dir_files(self, dirs, ext):
        fam = FAMILY.get(ext, (ext,))
        if not dirs or len(set(dirs)) > MAX_TARGETS:
            return []
        out = []
        for d in sorted(set(dirs)):
            out += [f for f in self.by_dir.get(d, ()) if os.path.splitext(f)[1] in fam]
        return sorted(out)[:MAX_DIR_TARGETS]

    def resolve(self, rel, imp):
        """Arquivos do repositorio que o import `imp`, escrito em `rel`, alcanca. [] se externo ou ambiguo."""
        ext = os.path.splitext(rel)[1]
        base = os.path.dirname(rel)
        try:
            if ext == ".py":
                return self._python(base, imp)
            if ext in JS_EXT:
                if imp.startswith("."):
                    return self._exact(os.path.join(base, imp), ext, ("index",))
                for a in JS_ALIASES:
                    if imp.startswith(a):
                        rest = imp[len(a):]
                        return self._exact(rest, ext, ("index",)) or self._suffix(rest, ext) or \
                            self._pick(self.by_suffix.get(rest.rstrip("/") + "/index", ()), ext)
                return []
            if ext in (".java", ".kt", ".scala"):
                if imp.endswith(".*") or imp.endswith("."):
                    return self._dir_files(self.dir_suffix.get(imp.rstrip(".*").replace(".", "/"), []), ext)
                return self._suffix(imp.replace(".", "/"), ext)
            if ext == ".cs":
                return self._dir_files(self.dir_dotted.get(imp, []), ext)
            if ext == ".go":
                segs = imp.split("/")
                for k in range(min(len(segs), MAX_SUFFIX), 0, -1):
                    dirs = self.dir_suffix.get("/".join(segs[-k:]))
                    if dirs:
                        return self._dir_files(dirs, ext)
                return []
            if ext == ".php":
                segs = imp.strip("\\").split("\\")
                for k in range(len(segs), 0, -1):
                    hit = self._suffix("/".join(segs[-k:]), ext)
                    if hit or k <= 2:
                        return hit
                return []
            if ext == ".rb":
                return self._exact(os.path.join(base, imp), ext) or self._suffix(imp, ext)
            if ext == ".dart":
                if imp.startswith("package:"):
                    rest = imp.split("/", 1)[1] if "/" in imp else ""
                    return self._suffix("lib/" + rest[:-5] if rest.endswith(".dart") else rest, ext) if rest else []
                if imp.startswith("dart:"):
                    return []
                return self._exact(os.path.join(base, imp), ext)
            if ext == ".rs":
                segs = [s for s in imp.split("::") if s]
                if not segs or segs[0] not in ("crate", "super", "self"):
                    return []
                path = segs[1:]
                for k in range(len(path), 0, -1):
                    p = "/".join(path[:k])
                    hit = self._suffix("src/" + p, ext) or self._suffix(p + "/mod", ext)
                    if hit:
                        return hit
                return []
        except (ValueError, IndexError):
            return []
        return []

    def _python(self, base, imp):
        if imp.startswith("."):
            dots = len(imp) - len(imp.lstrip("."))
            rest = imp[dots:]
            up = base
            for _ in range(dots - 1):
                up = os.path.dirname(up)
            stem = os.path.join(up, *rest.split(".")) if rest else up
            return self._exact(stem, ".py", ("__init__",))
        path = imp.replace(".", "/")
        return self._suffix(path, ".py") or self._pick(self.by_suffix.get(path + "/__init__", ()), ".py")
