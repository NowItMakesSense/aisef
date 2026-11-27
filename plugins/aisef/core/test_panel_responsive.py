#!/usr/bin/env python3
"""U-01: o painel em telas pequenas e baixas. Le index.html, sem navegador (a auditoria no navegador, de 320 a 1280 px,
ficou registrada no CHANGELOG). Guarda as regressoes que deixavam componentes inacessiveis:
- no celular, a barra inferior escondia Rastreabilidade, Historico e Engenharia (classe hide-m) e a busca sumia;
- cartao clicavel sem teclado, celula de mapa de riscos sem nome, alvos de toque abaixo de 24 px;
- cartoes com largura minima fixa que empurravam a pagina para o lado a 320 px (WCAG 1.4.10).
Uso: python3 -I test_panel_responsive.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
js = html[html.index("</style>"):]
fails = total = 0


def check(name, cond):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    fails += not cond


def media_blocks(cond):
    """Corpos dos @media com a condicao dada, na ordem do arquivo."""
    out, i = [], 0
    while True:
        i = css.find("@media (%s)" % cond, i)
        if i < 0:
            return out
        j = css.index("{", i) + 1
        depth, k = 1, j
        while depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        out.append((i, css[j:k - 1]))
        i = k


mobile = media_blocks("max-width: 760px")
hides = [pos for pos, body in mobile if re.search(r"\.rail \.hide-m[^{]*\{[^}]*display:\s*none", body)]
shows = [pos for pos, body in mobile if re.search(r"\.rail \.hide-m\s*\{[^}]*display:\s*grid", body)]
check("celular: a barra inferior mostra todas as telas (hide-m volta a aparecer depois de escondido)",
      bool(shows) and (not hides or max(shows) > max(hides)))
check("celular: a barra inferior rola na horizontal em vez de cortar telas",
      any(re.search(r"\.rail\s*\{[^}]*overflow-x:\s*auto", b) for _, b in mobile))
check("celular: botao de busca no topo, ligado a openSearch",
      'id="searchbtn"' in html and re.search(r'getElementById\("searchbtn"\)\.addEventListener\("click", openSearch\)', js)
      and any(re.search(r"\.searchbtn\s*\{[^}]*display:\s*grid", b) for _, b in mobile))
check("celular: o fim da pagina nao fica sob a barra inferior (padding maior que os 60 px da barra)",
      any(re.search(r"\.app\s*\{[^}]*padding-bottom:\s*calc\(7[2-9]px|\.app\s*\{[^}]*padding-bottom:\s*(7[2-9]|[89]\d)px", b)
          for _, b in mobile))
check("janela baixa: o trilho lateral rola na vertical",
      any(re.search(r"\.rail\s*\{[^}]*overflow-y:\s*auto", b) for _, b in media_blocks("max-height: 500px) and (min-width: 761px")))

small = re.search(r"([^{}]+)\{\s*min-height:\s*24px;\s*\}", css)
targets = small.group(1) if small else ""
for sel in ("button.chip", "button.pm-l", "button.rm-h", ".chain button.lk"):
    check("alvo de toque de 24 px: %s" % sel, sel in targets)
check("pontos e barras das linhas do tempo ganham area de toque de 24 px",
      re.search(r"\.tl-bar::after,\s*\.dl-dot::after\s*\{[^}]*height:\s*24px", css) is not None)

rm = re.search(r'el\("button", \{ cls: "rm-c[^;]*?\}\);', js, re.S)
check("celula do mapa de riscos tem nome acessivel (aria-label)", rm is not None and '"aria-label"' in rm.group(0))
tm = re.search(r'el\("div", \{ cls: "tm-card"[^\[]*', js, re.S)
check("cartao de agente rodando e focavel e e botao para o leitor de tela",
      tm is not None and 'role: run ? "button"' in tm.group(0) and 'tabindex: run ? "0"' in tm.group(0))
check("Enter e espaco acionam cartao role=button com data-agent/data-open",
      re.search(r'getAttribute\("role"\) === "button".*?data-agent.*?c\.click\(\)', js, re.S) is not None)

check("320 px: grade de licoes sem largura minima fixa maior que a tela",
      re.search(r"minmax\(300px", css) is None or re.search(r"\.lc\s*\{[^}]*minmax\(min\(300px, 100%\)", css) is not None)
check("320 px: cartao da saude do processo com coluna que encolhe", re.search(r"\.hc\s*\{\s*grid-template-columns:\s*minmax\(0, 1fr\)", css) is not None)
check("320 px: lista longa de criterios (AC-...) quebra linha", re.search(r"\.chain \.lk\s*\{[^}]*white-space:\s*normal", css) is not None)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
