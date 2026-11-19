#!/usr/bin/env python3
"""Contraste AA (WCAG 2.1) dos pares texto/fundo dos tokens do painel v3, nos temas claro e escuro.

Le o bloco `:root {` (claro) e o bloco `:root[data-theme="dark"] {` (escuro) de index.html; nao precisa de navegador.
Uso: python3 -I test_panel_contrast.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)


def tokens(block):
    return {k: v.upper() for k, v in re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\b", block)}


light_block = re.search(r"^:root \{(.*?)\n\}", css, re.S | re.M).group(1)
dark_block = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', css, re.S).group(1)
media_dark = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}', css, re.S).group(1)
THEMES = {"claro": tokens(light_block)}
THEMES["escuro"] = dict(THEMES["claro"], **tokens(dark_block))
same = tokens(dark_block) == tokens(media_dark)


def lum(hexc):
    def ch(i):
        c = int(hexc[1 + 2 * i:3 + 2 * i], 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(0) + 0.7152 * ch(1) + 0.0722 * ch(2)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (texto, fundo, minimo): 4.5 para texto; 3.0 para contorno de foco e glifos de estado
PAIRS = [("text", "ground", 4.5), ("text", "surface", 4.5), ("text", "raised", 4.5),
         ("muted", "ground", 4.5), ("muted", "surface", 4.5), ("muted", "raised", 4.5),
         ("faint", "surface", 4.5), ("faint", "ground", 4.5),
         ("run", "surface", 4.5), ("run", "run-soft", 4.5), ("done", "surface", 4.5), ("done", "done-soft", 4.5),
         ("you", "surface", 3.0), ("you", "you-soft", 4.5), ("fail", "surface", 4.5), ("fail", "fail-soft", 4.5),
         ("wait", "surface", 4.5), ("surface", "fail", 4.5),  # faixa de integridade comprometida: texto na cor da superficie
         ("run", "ground", 3.0)]  # anel de foco
fails = total = 0
total += 1
if not same:
    fails += 1
    print("FALHA os dois blocos escuros (prefers-color-scheme e data-theme) divergem")
else:
    print("OK    os dois blocos escuros (sistema e escolha explicita) tem os mesmos valores")
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
