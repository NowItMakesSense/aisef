/* AISEF ui_probe (V-05): roda dentro da pagina e mede o que da para medir sem opiniao.
   O ui_probe.py injeta este arquivo, chama as funcoes de window.__aisefProbe e faz os gestos reais (mouse, toque,
   teclado) pelo DevTools Protocol. Nenhuma funcao daqui altera a pagina, fora o contorno temporario da captura. */
(function () {
  if (window.__aisefProbe) return;
  const W = window, D = document;
  const els = [];                       // elementos que o Python pode citar pelo indice (pid), sem mexer no DOM
  const styleCache = new WeakMap();     // estilo de cada focavel antes do foco, para saber se o foco aparece
  const FOC = 'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),' +
              'textarea:not([disabled]),summary,iframe,[tabindex]:not([tabindex="-1"]),[contenteditable="true"]';
  const INTERACTIVE = FOC + ',[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[role=switch],[onclick]';

  function pid(e) { let i = els.indexOf(e); if (i < 0) { els.push(e); i = els.length - 1; } return i; }
  function sel(e) {
    if (!e || e === D.body) return 'body';
    const parts = [];
    for (let n = e; n && n.nodeType === 1 && n !== D.body && parts.length < 4; n = n.parentElement) {
      if (n.id && /^[A-Za-z][\w-]*$/.test(n.id)) { parts.unshift('#' + n.id); break; }
      let s = n.tagName.toLowerCase();
      const c = [...n.classList].filter(x => /^[A-Za-z_][\w-]*$/.test(x)).slice(0, 2);
      if (c.length) s += '.' + c.join('.');
      const p = n.parentElement;
      if (p) { const same = [...p.children].filter(x => x.tagName === n.tagName); if (same.length > 1) s += ':nth-of-type(' + (same.indexOf(n) + 1) + ')'; }
      parts.unshift(s);
    }
    return parts.join(' > ');
  }
  function label(e) {
    const t = (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent || e.value || '').trim().replace(/\s+/g, ' ');
    return t.length > 60 ? t.slice(0, 57) + '...' : t;
  }
  function kind(e) { return e.tagName.toLowerCase() + '.' + ([...e.classList][0] || '') + (e.getAttribute('role') ? '[' + e.getAttribute('role') + ']' : ''); }
  function shown(e) {
    const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false;
    if (e.checkVisibility && !e.checkVisibility({ opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true })) return false;  // details fechado
    for (let p = e; p && p.nodeType === 1; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse' || +cs.opacity === 0) return false;
      if (p.hasAttribute('inert') || p.getAttribute('aria-hidden') === 'true') return false;
    }
    return true;
  }
  function abs(r) { return { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) }; }
  function clipRect(e) {   // parte visivel do elemento depois dos ancestrais que cortam e da janela
    const r = e.getBoundingClientRect(); let L = r.left, T = r.top, R = r.right, B = r.bottom;
    for (let p = e.parentElement; p && p !== D.documentElement; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (/(hidden|clip|auto|scroll)/.test(cs.overflowX + ' ' + cs.overflowY)) {
        const q = p.getBoundingClientRect(); L = Math.max(L, q.left); T = Math.max(T, q.top); R = Math.min(R, q.right); B = Math.min(B, q.bottom);
      }
    }
    L = Math.max(L, 0); T = Math.max(T, 0); R = Math.min(R, innerWidth); B = Math.min(B, innerHeight);
    return { L, T, R, B, vis: Math.max(0, R - L) * Math.max(0, B - T), area: Math.max(1, r.width * r.height) };
  }
  function focusables(root) { return [...(root || D).querySelectorAll(FOC)].filter(e => e.tabIndex >= 0 && shown(e)); }
  function fullText(e) {   // o texto inteiro existe por outro caminho (dica, nome acessivel, expandir)?
    for (let n = e, i = 0; n && n.nodeType === 1 && i < 3; n = n.parentElement, i++) {
      if (n.getAttribute('title') || n.getAttribute('aria-label') || n.getAttribute('aria-description') ||
          n.getAttribute('aria-describedby') || n.getAttribute('data-tip') || n.getAttribute('data-tooltip')) return true;
      if (n.hasAttribute('aria-expanded')) return true;
    }
    return false;
  }
  function ownText(e) { let s = ''; for (const n of e.childNodes) if (n.nodeType === 3) s += n.textContent; return s.trim(); }
  function intersects(a, b) { return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom; }
  function scrollableAncestorX(e) {
    for (let p = e.parentElement; p && p !== D.body && p !== D.documentElement; p = p.parentElement) {
      if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(p).overflowX)) return p;
    }
    return null;
  }

  function reflow() {
    const out = [], vw = D.documentElement.clientWidth, over = D.documentElement.scrollWidth - vw;
    if (over > 1) {
      const culprits = [];
      for (const e of D.querySelectorAll('body *')) {
        if (!shown(e) || scrollableAncestorX(e)) continue;
        const r = e.getBoundingClientRect();
        if (r.right > vw + 1 && !(e.parentElement && e.parentElement.getBoundingClientRect().right > vw + 1 && e.parentElement !== D.body)) culprits.push(e);
      }
      out.push({ rule: 'UI-REFLOW', severity: 'high', certainty: 'high', pid: culprits[0] ? pid(culprits[0]) : null,
                 selector: culprits[0] ? sel(culprits[0]) : 'html', message: 'a pagina rola na horizontal: ' + over + ' px alem da tela' +
                 (culprits.length ? '; o que estoura: ' + culprits.slice(0, 3).map(sel).join(', ') : '') });
    }
    return out;
  }

  function clipped() {
    const out = [];
    for (const e of D.querySelectorAll('body *')) {
      if (!shown(e) || !ownText(e) && !(e.children.length === 0 && e.textContent.trim())) continue;
      const cs = getComputedStyle(e);
      const cutX = e.scrollWidth > e.clientWidth + 1 && /(hidden|clip)/.test(cs.overflowX);
      const cutY = e.scrollHeight > e.clientHeight + 2 && /(hidden|clip)/.test(cs.overflowY) && (cs.webkitLineClamp !== 'none' || e.clientHeight > 0);
      if (!(cutX || cutY) || /^(INPUT|SELECT|TEXTAREA|svg)$/i.test(e.tagName)) continue;
      const r = e.getBoundingClientRect(); if (r.width <= 2 || r.height <= 2) continue;   // so para leitor de tela (sr-only)
      if (fullText(e)) continue;
      const inCtl = e.closest(INTERACTIVE);   // dentro de um controle: abrir pode mostrar o texto inteiro
      out.push({ rule: 'UI-CLIPPED', severity: inCtl ? 'low' : 'medium', certainty: inCtl ? 'low' : cs.textOverflow === 'ellipsis' || cs.webkitLineClamp !== 'none' ? 'high' : 'medium',
                 pid: pid(e), selector: sel(e), group: kind(e),
                 message: 'texto cortado sem jeito de ler inteiro (sem dica, nome acessivel ou expandir): "' + label(e) + '"' + (inCtl ? '; esta dentro de um controle: confira se ele mostra o texto inteiro' : '') });
    }
    return out;
  }

  // conteudo que passa da borda de um conteiner que corta ou rola: o Python tenta cada gesto para alcanca-lo
  function hiddenOverflow() {
    const out = [];
    for (const e of D.querySelectorAll('body *')) {
      if (!shown(e) || !e.children.length) continue;
      const cs = getComputedStyle(e);
      const ox = e.scrollWidth > e.clientWidth + 2 && /(hidden|clip|auto|scroll)/.test(cs.overflowX);
      const oy = e.scrollHeight > e.clientHeight + 2 && /(hidden|clip|auto|scroll)/.test(cs.overflowY);
      if (!ox && !oy) continue;
      const box = e.getBoundingClientRect(); let lost = 0, interactive = 0;
      for (const k of e.querySelectorAll('*')) {
        if (k.children.length && !k.matches(INTERACTIVE)) continue;
        const r = k.getBoundingClientRect(); if (r.width < 1 || r.height < 1 || !shown(k)) continue;
        if (!intersects(r, box) || (ox && r.right > box.right + 1 && r.left >= box.right - r.width / 2) || (oy && r.bottom > box.bottom + 1 && r.top >= box.bottom - r.height / 2)) {
          if (k.textContent.trim() || k.matches(INTERACTIVE) || k.tagName === 'IMG') { lost++; if (k.matches(INTERACTIVE)) interactive++; }
        }
      }
      if (!lost) continue;
      if (e.parentElement && e.parentElement.querySelector('[aria-expanded]')) continue;   // tem "ver mais"
      const barH = e.offsetHeight - e.clientHeight - parseFloat(cs.borderTopWidth) - parseFloat(cs.borderBottomWidth);
      const barV = e.offsetWidth - e.clientWidth - parseFloat(cs.borderLeftWidth) - parseFloat(cs.borderRightWidth);
      const scrolls = { x: /(auto|scroll)/.test(cs.overflowX), y: /(auto|scroll)/.test(cs.overflowY) };
      out.push({ pid: pid(e), selector: sel(e), axis: ox ? 'x' : 'y', lost, interactive, scrolls,
                 bar: ox ? barH > 0 && cs.scrollbarWidth !== 'none' : barV > 0 && cs.scrollbarWidth !== 'none',
                 rect: abs(box), focusable: e.tabIndex >= 0 || !!e.querySelector(FOC) });
      if (out.length >= 30) break;
    }
    return out;
  }

  function hitArea(e) {   // lado da area que de fato responde ao toque, por elementFromPoint (conta ::before e ::after)
    let r = e.getBoundingClientRect();
    if (r.top < 0 || r.bottom > innerHeight || r.left < 0 || r.right > innerWidth) { e.scrollIntoView({ block: 'center', inline: 'center' }); r = e.getBoundingClientRect(); }
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2, own = t => t && (t === e || e.contains(t));
    for (const d of [12, 11, 9, 7, 5]) {
      if ([[cx - d, cy], [cx + d, cy], [cx, cy - d], [cx, cy + d]].every(([x, y]) => own(D.elementFromPoint(x, y)))) return 2 * d;
    }
    return Math.min(r.width, r.height);
  }
  function keepScroll(fn) {
    const sx = scrollX, sy = scrollY, inner = [...D.querySelectorAll('*')].filter(e => e.scrollLeft || e.scrollTop).map(e => [e, e.scrollLeft, e.scrollTop]);
    const out = fn();
    D.querySelectorAll('*').forEach(e => { if (e.scrollLeft || e.scrollTop) { e.scrollLeft = 0; e.scrollTop = 0; } });
    inner.forEach(([e, l, t]) => { e.scrollLeft = l; e.scrollTop = t; });
    W.scrollTo(sx, sy);
    return out;
  }
  function pinned(e) {   // dentro de barra fixa ou grudada: o conteudo rola por baixo dela de proposito
    for (let p = e; p && p.nodeType === 1; p = p.parentElement) { const ps = getComputedStyle(p).position; if (ps === 'fixed' || ps === 'sticky') return true; }
    return false;
  }
  function targets() {
    const out = [], list = [...D.querySelectorAll(INTERACTIVE)].filter(shown), rects = list.map(e => e.getBoundingClientRect());
    list.forEach((e, i) => {
      const r = rects[i]; if (r.width >= 24 && r.height >= 24) return;
      if (e.tagName === 'A' && e.parentElement && ownText(e.parentElement)) return;     // link dentro do texto: excecao do 2.5.8
      if (/^(INPUT)$/.test(e.tagName) && /^(checkbox|radio)$/.test(e.type) && e.closest('label')) return;
      if (hitArea(e) >= 22) return;   // a area de toque (::after, padding) ja tem 24 px
      const q = e.getBoundingClientRect(), cx = q.left + q.width / 2, cy = q.top + q.height / 2;
      const zone = { left: cx - 12, right: cx + 12, top: cy - 12, bottom: cy + 12 };
      const clash = list.some((o, j) => j !== i && !o.contains(e) && !e.contains(o) && intersects(zone, o.getBoundingClientRect()));
      if (!clash) return;
      out.push({ rule: 'UI-TARGET', severity: 'medium', certainty: 'high', pid: pid(e), selector: sel(e), group: kind(e),
                 message: 'alvo de ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' px, menor que 24x24 e sem espaco livre em volta: "' + label(e) + '"' });
    });
    return out;
  }

  function overlap() {
    const out = [], leaves = [];
    for (const e of D.querySelectorAll('body *')) {   // so a parte visivel (depois dos conteineres que cortam)
      if (!ownText(e) || !shown(e) || pinned(e)) continue;
      const c = clipRect(e); if (c.vis < 1) continue;
      leaves.push([e, { left: c.L, right: c.R, top: c.T, bottom: c.B, width: c.R - c.L, height: c.B - c.T }]);
      if (leaves.length > 800) break;
    }
    const seen = new Set();
    for (let i = 0; i < leaves.length; i++) for (let j = i + 1; j < leaves.length; j++) {
      const [a, ra] = leaves[i], [b, rb] = leaves[j];
      if (!intersects(ra, rb) || a.contains(b) || b.contains(a)) continue;
      const iw = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left), ih = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
      const small = Math.min(ra.width * ra.height, rb.width * rb.height);
      if (iw * ih < 0.3 * small || ih < 4) continue;
      const pa = getComputedStyle(a).position, pb = getComputedStyle(b).position;
      if (pa === 'absolute' || pb === 'absolute' || pa === 'fixed' || pb === 'fixed') continue;   // selo e sobreposicao de proposito
      const k = kind(a) + '|' + kind(b); if (seen.has(k)) continue; seen.add(k);
      out.push({ rule: 'UI-OVERLAP', severity: 'medium', certainty: 'medium', pid: pid(a), selector: sel(a), group: k,
                 message: 'texto sobreposto: "' + label(a) + '" e "' + label(b) + '" (' + sel(b) + ')' });
      if (out.length >= 20) return out;
    }
    return out;
  }

  function hoverOnly() {
    const out = [], hov = [], foc = new Set(), alt = new Set();
    const STATE = /(:focus|:focus-within|:focus-visible|\[open\]|\[aria-expanded|\.(open|on|show|shown|active|expanded|visible|is-open)\b|:target|:checked)/;
    const last = t => t.split(/\s*[ >~+]\s*/).pop().replace(/:[\w-]+(\([^)]*\))?/g, '');
    for (const sh of D.styleSheets) {
      let rules; try { rules = sh.cssRules; } catch (e) { continue; }
      const walk = rs => { for (const r of rs) { if (r.cssRules && !r.selectorText) { walk(r.cssRules); continue; } if (!r.selectorText) continue;
        for (const s of r.selectorText.split(',')) {
          const t = s.trim();
          if (/:focus(-within|-visible)?/.test(t)) foc.add(t.replace(/:focus(-within|-visible)?/g, ':hover'));
          if (!/:hover/.test(t) && STATE.test(t) && /(display|visibility|opacity)/.test(r.style.cssText)) alt.add(last(t));
          if (/:hover/.test(t) && /(display|visibility|opacity|max-height|transform)/.test(r.style.cssText) && /:hover\s*[ >~+]\s*\S/.test(t)) hov.push([t, r.style.cssText]);
        } } };
      walk(rules);
    }
    for (const [t, css] of hov) {
      if (foc.has(t) || alt.has(last(t))) continue;   // ha regra do mesmo alvo para foco, clique ou estado aberto
      let el; try { el = D.querySelector(t.replace(/:hover/g, '')); } catch (e) { continue; }
      if (!el || !/(display|visibility|opacity)/.test(css)) continue;
      out.push({ rule: 'UI-HOVER-ONLY', severity: 'medium', certainty: 'medium', pid: pid(el), selector: t, group: t,
                 message: 'conteudo que so aparece no hover (' + t + '), sem regra equivalente para :focus ou :focus-within' });
      if (out.length >= 10) break;
    }
    return out;
  }

  function pointerOnly() {   // tem cara de clicavel, mas o teclado nao chega
    const out = [];
    for (const e of D.querySelectorAll('body *')) {
      if (!shown(e) || e.matches(FOC) || e.closest(FOC) || e.closest('label') || e.querySelector(FOC)) continue;
      const cs = getComputedStyle(e), pc = e.parentElement ? getComputedStyle(e.parentElement).cursor : '';
      const looks = (cs.cursor === 'pointer' && pc !== 'pointer') || e.hasAttribute('onclick') || /^(button|link|tab|menuitem)$/.test(e.getAttribute('role') || '');
      if (!looks) continue;
      out.push({ pid: pid(e), selector: sel(e), group: kind(e), label: label(e) });
      if (out.length >= 30) break;
    }
    return out;
  }

  function clickables(origin) {
    const BAD = /(excluir|apagar|deletar|delete|remov|sair|logout|sign ?out|pagar|comprar|checkout|enviar|submit|send|publicar)/i;
    const seen = {}, out = [];
    const list = [...D.querySelectorAll(INTERACTIVE)].filter(shown).concat(pointerOnly().map(x => els[x.pid]));
    for (const e of list) {
      const k = kind(e); if (seen[k]) continue;
      if (e.matches('input,select,textarea,iframe,[contenteditable="true"]')) continue;
      if ((e.getAttribute('aria-current') && e.getAttribute('aria-current') !== 'false') || e.getAttribute('aria-selected') === 'true') continue;   // ja e o atual
      if (e.tagName === 'A' && e.href && e.href === location.href) continue;   // link para onde ja esta
      const looks = /^(A|BUTTON|SUMMARY)$/.test(e.tagName) || e.hasAttribute('role') || e.hasAttribute('onclick') || getComputedStyle(e).cursor === 'pointer';
      if (!looks) continue;   // so tabindex (conteiner focavel): nao promete clique
      let skip = '';
      if (e.closest('[data-probe-skip]')) skip = 'data-probe-skip';
      else if (e.type === 'submit' || (e.tagName === 'BUTTON' && e.form && e.getAttribute('type') !== 'button')) skip = 'envia formulario';
      else if (BAD.test(label(e))) skip = 'acao destrutiva ou externa pelo texto';
      else if (e.tagName === 'A' && (e.target === '_blank' || e.hasAttribute('download') || (e.href && new URL(e.href, location.href).origin !== origin))) skip = 'link externo ou download';
      seen[k] = 1;
      const r = e.getBoundingClientRect();
      out.push({ pid: pid(e), selector: sel(e), group: k, label: label(e), skip, native: /^(A|BUTTON|SUMMARY)$/.test(e.tagName),
                 link: e.tagName === 'A' && !!e.getAttribute('href'), rect: abs(r) });
      if (out.length >= 40) break;
    }
    return out;
  }

  function cacheFocusStyles() {
    for (const e of focusables()) {
      const cs = getComputedStyle(e);
      styleCache.set(e, [cs.outlineStyle + cs.outlineWidth, cs.boxShadow, cs.backgroundColor, cs.borderColor, cs.color, cs.textDecorationLine].join('|'));
    }
  }

  function focusInfo() {
    const e = D.activeElement;
    if (!e || e === D.body || e === D.documentElement) return { none: true };
    const c = clipRect(e), cs = getComputedStyle(e);
    const now = [cs.outlineStyle + cs.outlineWidth, cs.boxShadow, cs.backgroundColor, cs.borderColor, cs.color, cs.textDecorationLine].join('|');
    const ring = (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== 'none';
    let covered = null;
    if (c.vis > 0) {
      const pts = [[(c.L + c.R) / 2, (c.T + c.B) / 2], [c.L + 2, c.T + 2], [c.R - 2, c.B - 2]];
      let hidden = 0;
      for (const [x, y] of pts) { const t = D.elementFromPoint(x, y); if (t && !e.contains(t) && !t.contains(e) && !(t.closest('label') && t.closest('label').contains(e))) { hidden++; covered = t; } }
      if (hidden < 2) covered = null;
    }
    return { pid: pid(e), selector: sel(e), label: label(e), group: kind(e), visible: c.vis / c.area,
             indicator: ring || (styleCache.has(e) && styleCache.get(e) !== now), covered: covered ? sel(covered) : null };
  }

  function sig() {   // assinatura do estado da pagina: muda quando um controle faz alguma coisa
    let h = 0; const s = D.body ? D.body.innerHTML : '';
    for (let i = 0; i < s.length; i += Math.max(1, s.length >> 14)) h = (h * 31 + s.charCodeAt(i)) | 0;
    const vals = [...D.querySelectorAll('input,select,textarea')].map(e => e.type === 'checkbox' || e.type === 'radio' ? e.checked : e.value).join('|');
    const aria = [...D.querySelectorAll('[aria-expanded],[aria-pressed],[aria-selected],[aria-checked],[open]')].map(e => (e.getAttribute('aria-expanded') || '') + (e.getAttribute('aria-pressed') || '') + (e.getAttribute('aria-selected') || '') + (e.getAttribute('aria-checked') || '') + e.hasAttribute('open')).join('');
    const scr = [...D.querySelectorAll('*')].filter(e => e.scrollLeft || e.scrollTop).map(e => e.scrollLeft + ',' + e.scrollTop).join(';');
    const act = D.activeElement && D.activeElement !== D.body ? sel(D.activeElement) : '';
    const root = [...D.documentElement.attributes].map(a => a.name + '=' + a.value).join(' ');
    const vis = act + '@' + root + '@' + [...D.querySelectorAll(INTERACTIVE)].filter(shown).length + ':' + openDialogs().length;
    return [location.href, s.length, h, vals, aria, scr, vis, scrollX + ',' + scrollY, D.documentElement.className, D.body && D.body.className].join('#');
  }
  function openDialogs() { return [...D.querySelectorAll('dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]')].filter(shown).map(sel); }

  function scrollState(i) {   // posicao do conteudo de um conteiner: rolagem dele e dos filhos, e onde o 1o filho esta
    const e = els[i]; if (!e) return null;
    const first = e.firstElementChild ? e.firstElementChild.getBoundingClientRect() : { left: 0, top: 0 };
    let inner = 0; for (const k of e.querySelectorAll('*')) inner += k.scrollLeft + k.scrollTop;
    return [e.scrollLeft, e.scrollTop, inner, Math.round(first.left), Math.round(first.top), getComputedStyle(e.firstElementChild || e).transform].join(',');
  }
  function center(i) {
    const e = els[i]; if (!e) return null; e.scrollIntoView({ block: 'center', inline: 'nearest' });
    const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, t = D.elementFromPoint(x, y);
    return { x, y, w: r.width, h: r.height, hit: !!t && (t === e || e.contains(t) || t.contains(e)) };
  }
  function rectOf(i) { const e = els[i]; return e && shown(e) ? abs(e.getBoundingClientRect()) : null; }
  function resolve(css) { const e = D.querySelector(css); return e ? pid(e) : null; }
  function focusInside(i) { const e = els[i]; if (!e) return false; const f = e.tabIndex >= 0 ? e : e.querySelector(FOC); if (!f) return false; f.focus(); return D.activeElement === f; }
  function mark(r) {
    unmark(); const m = D.createElement('div'); m.id = '__aisef_mark';
    m.style.cssText = 'position:absolute;z-index:2147483647;pointer-events:none;outline:3px solid #e5484d;outline-offset:2px;background:rgba(229,72,77,.08);' +
      'left:' + r.x + 'px;top:' + r.y + 'px;width:' + Math.max(4, r.w) + 'px;height:' + Math.max(4, r.h) + 'px';
    D.body.appendChild(m);
  }
  function unmark() { const m = D.getElementById('__aisef_mark'); if (m) m.remove(); }
  function motion() {
    if (!D.getAnimations) return [];
    return D.getAnimations().filter(a => a.playState === 'running').map(a => {
      const t = a.effect && a.effect.getComputedTiming ? a.effect.getComputedTiming() : {};
      return { target: a.effect && a.effect.target ? sel(a.effect.target) : '?', duration: t.duration, iterations: t.iterations, name: a.animationName || a.transitionProperty || '' };
    }).filter(a => a.iterations === Infinity || a.duration >= 1000);
  }

  W.__aisefProbe = {
    static: () => { cacheFocusStyles(); return { findings: reflow().concat(clipped(), overlap(), hoverOnly(), keepScroll(targets)), overflow: hiddenOverflow(),
                                                 pointerOnly: pointerOnly(), focusables: focusables().map(pid), page: { w: D.documentElement.scrollWidth, h: D.documentElement.scrollHeight } }; },
    focusList: () => { cacheFocusStyles(); return focusables().map(pid); },
    clickables, focusInfo, sig, openDialogs, scrollState, center, rectOf, resolve, focusInside, mark, unmark, motion,
    sel: i => els[i] ? sel(els[i]) : null, active: () => D.activeElement ? pid(D.activeElement) : null,
    blur: () => { if (D.activeElement && D.activeElement.blur) D.activeElement.blur(); W.scrollTo(0, 0); },
  };
})();
