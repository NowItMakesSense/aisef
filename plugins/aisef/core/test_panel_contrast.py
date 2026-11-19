#!/usr/bin/env python3
"""Contraste AA (WCAG 2.1) dos pares texto/fundo dos tokens do painel, nos temas claro e escuro.

Le o bloco :root e o bloco dark de index.html; nao precisa de navegador. Uso: python3 -I test_panel_contrast.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)


def tokens(block):
    return {k: v.upper() for k, v in re.findall(r"--([a-z0-9-]+):(#[0-9A-Fa-f]{6})", block)}


light_block = re.search(r":root\{color-scheme.*?\}", css, re.S).group(0)
dark_block = re.search(r"prefers-color-scheme:dark\)\{:root\{(.*?)\}\}", css, re.S).group(1)
THEMES = {"claro": tokens(light_block)}
THEMES["escuro"] = dict(THEMES["claro"], **tokens(dark_block))


def lum(hexc):
    def ch(i):
        c = int(hexc[1 + 2 * i:3 + 2 * i], 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(0) + 0.7152 * ch(1) + 0.0722 * ch(2)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (texto, fundo, minimo): 4.5 para texto, 3 para componentes graficos (anel de foco)
PAIRS = [("ink", "bg", 4.5), ("ink", "surface", 4.5), ("ink", "surface-2", 4.5), ("muted", "bg", 4.5), ("muted", "surface", 4.5),
         ("muted", "surface-2", 4.5), ("ledger", "surface", 4.5), ("ledger", "ledger-soft", 4.5), ("ledger", "bg", 4.5),
         ("amber", "surface", 4.5), ("amber", "amber-soft", 4.5), ("deny", "surface", 4.5), ("deny", "deny-soft", 4.5),
         ("idle", "surface", 4.5), ("idle", "bg", 4.5), ("on-ledger", "ledger", 4.5), ("on-deny", "deny", 4.5), ("focus", "bg", 3.0), ("focus", "surface", 3.0)]
fails = total = 0
for theme, t in THEMES.items():
    for fg, bg, need in PAIRS:
        total += 1
        if fg not in t or bg not in t:
            print("FALHA token ausente:", theme, fg, bg)
            fails += 1
            continue
        r = ratio(t[fg], t[bg])
        ok = r >= need
        fails += not ok
        print(("OK    " if ok else "FALHA ") + "%s: %s sobre %s = %.2f:1 (minimo %.1f)" % (theme, fg, bg, r, need))
print("\n%d verificacoes de contraste, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
