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

# ---- U-02: usabilidade dos componentes (achados testando clique, foco e rolagem no navegador)
check("sem integrity-slot vazio no main (abria 20 px em branco no topo de toda tela)",
      "integrity-slot" not in html and 'id="integrity-src"' not in js)
check("aviso de integridade e de contrato invalido criados so quando ha o que avisar, com estilo (.ibox)",
      re.search(r"if \(boxes\.length\)", js) is not None and re.search(r"\.ibox\.warning\s*\{", css) is not None)
fb = re.search(r"\.fb-list\s*\{([^}]*)\}", css)
check("pilulas de feature numa linha so, arrastaveis como o mapa (PAN) e com a roda do mouse",
      fb is not None and "overflow-x: auto" in fb.group(1) and "flex-wrap" not in fb.group(1)
      and re.search(r'var PAN = "[^"]*\.fb-list', js) is not None
      and re.search(r'addEventListener\("wheel", function \(e\) \{\s*var w = e\.target\.closest && e\.target\.closest\("\.fb-list"\)', js) is not None)
check("pilulas: esmaecido so do lado em que ha mais, e a escolhida volta a vista so quando a escolha muda",
      "function fbFade(w)" in js and re.search(r"key !== fbSel", js) is not None and re.search(r"\.fb-list\.fade-l\.fade-r", css) is not None)
check("pilula de feature com nome completo (id, titulo e estado)", re.search(r'cls: "fb-f"[^\n]*\n\s*"aria-label": f \+', js) is not None)
hidden = [m.group(1).strip().splitlines()[-1] for m in re.finditer(r"([^{}]+)\{[^}]*scrollbar-width: none", css)]
check("so as pilulas (que tem arraste, roda e Tab) rolam com a barra escondida", hidden == [".fb-list"])
check("dica (data-tip) aparece tambem no foco do teclado e no toque",
      'addEventListener("focusin"' in js and re.search(r'addEventListener\("pointerdown", function \(e\) \{ if \(e\.pointerType === "mouse"\) return; var n = tipFor\(e\.target\)', js) is not None)
check("texto cortado (inteiro so no title) vira dica no foco e no toque", "function tipTitle(n)" in js and 'getAttribute("data-tip") || tipTitle(n)' in js)
check("gaveta devolve o foco a quem a abriu", "function restoreFocus()" in js and re.search(r"if \(had\) restoreFocus\(\)", js) is not None
      and js.count("rememberOpener();") == 2)
check("ponto de atencao do mapa abre com clique e teclado (aria-expanded)",
      re.search(r'bt\.addEventListener\("click", function \(\) \{\s*var on = !mx\.classList\.contains\("open"\)', js) is not None and '"aria-expanded": "false" }, [icon(r[0])]' in js)
check("tipo de decisao (texto SVG com role=button) responde a Enter e espaco",
      re.search(r'lt\.addEventListener\("keydown", function \(e\) \{ if \(e\.key === "Enter" \|\| e\.key === " "\)', js) is not None)
check("pontos de Entregas no tempo nao ficam um sobre o outro (dodgeDots depois do layout)",
      "function dodgeDots()" in js and re.search(r"function markPan\(\)[^\n]*dodgeDots\(\)", js) is not None)
check("chip de tarefa fora do quadro (T-MAINT) nao finge ser botao",
      re.search(r'byId\(t\.task_id\) \? el\("button", \{ cls: "chip"', js) is not None)
check("foco nao fica sob o topo fixo nem sob a barra inferior do celular (scroll-padding, WCAG 2.4.11)",
      re.search(r"html \{ scroll-padding-top:", css) is not None
      and any(re.search(r"html \{ scroll-padding-bottom:", b) for _, b in media_blocks("max-width: 760px")))
check("foco nas raias nao fica sob a coluna de rotulos fixa", re.search(r"\.lanes \{ scroll-padding-left:", css) is not None)
check("barra da raia focada fica acima dos marcadores, e o marcador tem dica acessivel (nao so title)",
      re.search(r"\.tl-bar:hover, \.tl-bar:focus-visible \{[^}]*z-index: 4", css) is not None
      and re.search(r'cls: "tl-mk " \+ ST\[k\[0\]\]\.txt, style: [^}]*"data-tip"', js) is not None)
check("gaveta devolve o foco a um alvo visivel (no celular o mapa escondido tem os mesmos data-open)",
      "n.getClientRects().length > 0" in js)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
