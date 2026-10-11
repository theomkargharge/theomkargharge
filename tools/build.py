#!/usr/bin/env python3
"""
Builds the animated SVG cards used by the profile README.

Every card is built twice, into assets/dark and assets/light. The cards have
transparent backgrounds so they sit on whatever GitHub theme the visitor uses;
README.md picks the matching variant with <picture>.

Everything the cards say lives in the CONTENT section below. Edit it, then run:

    python3 tools/build.py

Runs on the standard library alone. If fontTools is installed
(pip install fonttools brotli), each card embeds only the glyphs it uses,
which makes the files roughly 3x smaller.

Fonts: Geist, Geist Mono, Instrument Serif (SIL OFL 1.1), pre-subset in tools/fonts.
Brand icons: Simple Icons (CC0), in tools/icons.
"""
import base64
import io
import json
import math
import os
import re
from contextlib import contextmanager
from xml.sax.saxutils import escape

try:
    from fontTools import subset as _ft_subset
    from fontTools.ttLib import TTFont as _TTFont
except ImportError:  # still works, just embeds the full (Latin) font files
    _ft_subset = None

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), 'assets')

# ════════════════════════════════════════════════════════════════════════════
# CONTENT
# ════════════════════════════════════════════════════════════════════════════

NAME_FIRST, NAME_LAST = 'Omkar', 'Gharge'
EYEBROW = 'FLUTTER & GENAI ENGINEER  /  PUNE, INDIA'
TAGLINE = [('Mobile apps for ', 'millions,'), ('made smarter with ', 'AI.')]
EMAIL = 'omkarghargeog@gmail.com'

STATS = [  # (value, label line 1, label line 2)
    ('3.5+', 'YEARS SHIPPING', 'FLUTTER'),
    ('1M+', 'DOWNLOADS ON', 'ONE APP'),
    ('4', 'APPS LIVE ON', 'THE STORES'),
    ('6', 'PAYMENT', 'GATEWAYS'),
]

TERMINAL = [
    'flutter build ipa --release',
    'flutter build appbundle --release',
    'docker compose up -d tryware-api',
    'git push origin main',
]

CODE = """/// Mobile apps for millions, made smarter with AI.
class OmkarGharge extends Engineer {
  final role = 'Flutter & GenAI Engineer';
  final basedIn = 'Pune, India';
  final yearsShipping = 3.5;

  final shipped = const {
    'Akbar Travels': 'Flights & hotels · 1M+ downloads · iOS + Android',
    'TryWare AI': 'GenAI virtual try-on · built solo, idea to Play Store',
    'Buggy': 'Ride-hailing · rider + driver apps · live tracking',
  };

  final stack = const {
    'mobile': ['Flutter', 'Dart', 'Swift', 'GetX', 'Riverpod', 'Bloc'],
    'genai': ['LangChain', 'LangGraph', 'RAG', 'AI Agents', 'OpenAI'],
    'backend': ['FastAPI', 'Firebase', 'Supabase', 'WebSocket', 'Docker'],
    'payments': ['Razorpay', 'PhonePe', 'Apple Pay', 'Tabby', 'Tamara'],
  };

  @override
  Future<void> build() => ship(apps: forMillions, madeSmarterWith: ai);
}"""

EXPERIENCE = [
    {
        'period': 'JAN 2025 — PRESENT', 'current': True,
        'role': 'Flutter Developer', 'company': 'Benzy Infotech', 'detail': 'Akbar Travels Group',
        'points': [
            'Build and ship Akbar Travels: Flights & Hotels — 1M+ downloads on iOS and Android.',
            'Real-time AI support chatbot over WebSocket, with instant hand-off to live agents.',
            'Razorpay, Tamara & Tabby checkout · CleverTap push · deep links · Hive storage.',
        ],
    },
    {
        'period': 'JUN 2023 — DEC 2024', 'current': False,
        'role': 'Flutter Developer', 'company': 'Movilidad Technologies', 'detail': 'Travel & Mobility',
        'points': [
            'Built the Buggy rider app and Buggy Sarathi driver app from scratch.',
            'Live Google Maps tracking with battery-efficient background location — engagement up 25%.',
            'WebSocket real-time layer that cut data-sync delays by 30%.',
        ],
    },
    {
        'period': '2019 — 2023', 'current': False, 'education': True,
        'role': 'B.Tech, Computer Science & Engineering',
        'points': ['Dr. Babasaheb Ambedkar Technological University · CGPA 8.47'],
    },
]

STACK = [  # (title, [(label, simple-icons slug or None)])
    ('Mobile', [('Flutter', 'flutter'), ('Dart', 'dart'), ('Swift', 'swift'), ('Java', 'openjdk'),
                ('GetX', None), ('Riverpod', None), ('Provider', None), ('Bloc', None), ('Hive', None)]),
    ('Generative AI', [('LangChain', 'langchain'), ('LangGraph', 'langchain'), ('RAG', None), ('AI Agents', None),
                       ('OpenAI', None), ('Gemini', 'googlegemini'), ('Embeddings', None), ('Vector DBs', None)]),
    ('Backend & Cloud', [('Python', 'python'), ('FastAPI', 'fastapi'), ('Firebase', 'firebase'),
                         ('Supabase', 'supabase'), ('WebSocket', None), ('REST', None), ('AWS S3', None),
                         ('Cloudflare', 'cloudflare'), ('Docker', 'docker'), ('GitHub Actions', 'githubactions')]),
    ('Payments', [('Razorpay', 'razorpay'), ('PhonePe', 'phonepe'), ('Apple Pay', 'applepay'),
                  ('Checkout.com', None), ('Tabby', None), ('Tamara', None)]),
    ('Integrations', [('CleverTap', None), ('Google Maps', 'googlemaps'), ('Places API', 'googlemaps'),
                      ('AdMob', 'googleadmob'), ('Push / FCM', 'firebase'), ('Deep links', None),
                      ('Shiprocket', None), ('Porter', None)]),
    ('Tooling', [('Claude Code', 'claude'), ('Xcode', 'xcode'), ('Android Studio', 'androidstudio'),
                 ('VS Code', None), ('Postman', 'postman'), ('Git', 'git'), ('GitHub', 'github'),
                 ('Bitbucket', 'bitbucket')]),
]

# ════════════════════════════════════════════════════════════════════════════
# THEMES  (brand from theomkargharge.github.io/Portfolio)
# ════════════════════════════════════════════════════════════════════════════
# Card backgrounds are transparent, so the dark palette must read on every dark
# GitHub theme (#0d1117 default, #212830 dimmed, #010409 high contrast) and the
# light palette on white.

THEMES = {
    'dark': dict(
        FG='#f4f4f5', FG2='#b4b4bd', FG3='#8e8e99', FG4='#6e6e79', INK='255,255,255',
        LINE='rgba(255,255,255,.09)', LINE2='rgba(255,255,255,.15)', SURFACE='rgba(255,255,255,.04)',
        GLASS='rgba(22,22,28,.92)', GLASS_STROKE='rgba(255,255,255,.16)', NODE='rgba(255,255,255,.05)',
        WINDOW='rgba(1,4,9,.42)', BTN='rgba(255,255,255,.05)', BTN_STROKE='rgba(255,255,255,.18)',
        BLUE='#8ec5ff', VIOLET='#b4a2ff', PINK='#f5b8ff', GREEN='#4ade80', AMBER='#fcd9a8', MINT='#93e5c4',
        GRAD=('#8ec5ff', '#b4a2ff', '#f5b8ff'),
        GREEN_BG='rgba(74,222,128,.08)', GREEN_STROKE='rgba(74,222,128,.32)', GREEN_TEXT='#bbf7d0',
        HILITE='rgba(180,162,255,.07)', GLOW=1.0, SHADOW=.5,
        SYNTAX=dict(comment='#6e6e7a', ident='#e4e4e7', fn='#93e5c4', named='#c7d2fe'),
    ),
    'light': dict(
        FG='#18181b', FG2='#52525b', FG3='#6b6b75', FG4='#9a9aa4', INK='0,0,0',
        LINE='rgba(0,0,0,.08)', LINE2='rgba(0,0,0,.13)', SURFACE='rgba(0,0,0,.025)',
        GLASS='rgba(255,255,255,.94)', GLASS_STROKE='rgba(0,0,0,.1)', NODE='#ffffff',
        WINDOW='#ffffff', BTN='#ffffff', BTN_STROKE='rgba(0,0,0,.15)',
        BLUE='#2f74d0', VIOLET='#6d4fe0', PINK='#c0399f', GREEN='#16a34a', AMBER='#b45309', MINT='#0f8a6a',
        GRAD=('#3d7be0', '#7656f0', '#cf4bbd'),
        GREEN_BG='rgba(22,163,74,.08)', GREEN_STROKE='rgba(22,163,74,.32)', GREEN_TEXT='#15803d',
        HILITE='rgba(109,79,224,.07)', GLOW=.6, SHADOW=.16,
        SYNTAX=dict(comment='#9a9aa5', ident='#27272a', fn='#0f766e', named='#4338ca'),
    ),
}
PASTEL = ('#8ec5ff', '#b4a2ff', '#f5b8ff')   # brand gradient on dark surfaces, in both themes
THEME = 'dark'


def apply_theme(name):
    global THEME
    THEME = name
    globals().update(THEMES[name])


@contextmanager
def theme(name):
    """Temporarily switch palette, e.g. for objects that stay dark in both themes (phone, map)."""
    prev = THEME
    apply_theme(name)
    try:
        yield
    finally:
        apply_theme(prev)


apply_theme('dark')

# Type scale. Cards are 1200 wide and GitHub shows them ~850px wide, so
# these render at roughly 70%: 14.5 → 10px labels, 19 → 13px body copy.
LABEL, META, BODY, CHIP = 14.5, 14, 19, 14.5
M = 8   # side margin; cards are borderless so content lines up with the README column

FAM = {'s': 'G', 'm': 'GM', 'i': 'IS'}
FONT_FILES = {'G': ('geist', 'normal', '100 900'),
              'GM': ('geistmono', 'normal', '100 900'),
              'IS': ('iserif-italic', 'italic', '400')}
METRICS = json.load(open(os.path.join(HERE, 'fonts', 'metrics.json')))
ICON_COLORS = json.load(open(os.path.join(HERE, 'icons', 'colors.json')))
USED = {k: set() for k in FONT_FILES}   # glyphs used by the card being built


def use(f, text):
    USED[FAM[f]].update(text)


def font_css():
    """@font-face rules for the fonts the current card used; resets the tracker."""
    rules = []
    for fam, chars in USED.items():
        if not chars:
            continue
        name, style, weight = FONT_FILES[fam]
        path = os.path.join(HERE, 'fonts', name + '.woff2')
        if _ft_subset:
            opts = _ft_subset.Options()
            opts.flavor, opts.layout_features = 'woff2', ['kern', 'liga', 'calt']
            font = _TTFont(path)
            sub = _ft_subset.Subsetter(opts)
            sub.populate(text=''.join(chars) + ' ')
            sub.subset(font)
            buf = io.BytesIO()
            font.flavor = 'woff2'
            font.save(buf)
            data = buf.getvalue()
        else:
            with open(path, 'rb') as fh:
                data = fh.read()
        rules.append("@font-face{font-family:%s;src:url(data:font/woff2;base64,%s) format('woff2');"
                     "font-style:%s;font-weight:%s}" % (fam, base64.b64encode(data).decode(), style, weight))
        chars.clear()
    return ''.join(rules)


def tw(text, f='s', size=16, weight=400, ls=0):
    """Advance width of a run of text, from the embedded fonts' metrics."""
    table = METRICS[FONT_FILES[FAM[f]][0]]
    adv = table[min(table, key=lambda k: abs(int(k) - weight))]
    return sum(adv.get(ch, 0.6) for ch in text) * size + ls * len(text)


def n(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.') if isinstance(v, float) else str(v)


def ink(a):
    return f'rgba({INK},{a})'


def T(x, y, s, f='s', size=16, w=400, fill=None, anchor=None, ls=None, cls='', extra=''):
    use(f, s)
    attrs = f' text-anchor="{anchor}"' if anchor else ''
    if ls:
        attrs += f' letter-spacing="{n(ls)}"'
    klass = f'{f} {cls}'.strip()
    return (f'<text x="{n(x)}" y="{n(y)}" class="{klass}" font-size="{n(size)}" font-weight="{w}" '
            f'fill="{fill or FG}"{attrs}{extra}>{escape(s)}</text>')


def runs(x, y, parts, anchor='start'):
    """Mixed-font text on one baseline. parts: (text, f, size, weight, fill[, ls])."""
    widths = [tw(p[0], p[1], p[2], p[3], p[5] if len(p) > 5 else 0) for p in parts]
    x -= {'start': 0, 'middle': sum(widths) / 2, 'end': sum(widths)}[anchor]
    out = []
    for p, wd in zip(parts, widths):
        out.append(T(x, y, p[0], p[1], p[2], p[3], p[4], ls=p[5] if len(p) > 5 else None))
        x += wd
    return ''.join(out), x


def wrap(text, f, size, weight, maxw):
    lines, cur = [], ''
    for word in text.split(' '):
        trial = f'{cur} {word}'.strip()
        if cur and tw(trial, f, size, weight) > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


def fit(text, f, size, weight, maxw, ls=0):
    """Largest size ≤ `size` at which `text` fits in `maxw`."""
    while size > 8 and tw(text, f, size, weight, ls) > maxw:
        size -= .5
    return size


def _lum(r, g, b):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    return .2126 * ch(r) + .7152 * ch(g) + .0722 * ch(b)


def brand(hexc):
    """Brand colour nudged until it reads on the current theme's background."""
    r, g, b = (int(hexc[i:i + 2], 16) for i in (0, 2, 4))
    if THEME == 'dark':
        while _lum(r, g, b) < .17:
            r, g, b = (int(c + (255 - c) * .16) for c in (r, g, b))
    else:
        while _lum(r, g, b) > .4:
            r, g, b = (int(c * .85) for c in (r, g, b))
    return '#%02x%02x%02x' % (r, g, b)


_ICONS = {}


def icon(slug, x, y, size, color=None):
    if slug not in _ICONS:
        with open(os.path.join(HERE, 'icons', slug + '.svg')) as fh:
            _ICONS[slug] = re.search(r' d="([^"]+)"', fh.read()).group(1)
    color = color or brand(ICON_COLORS[slug])
    return f'<path transform="translate({n(x)} {n(y)}) scale({n(size / 24)})" d="{_ICONS[slug]}" fill="{color}"/>'


def sparkle(cx, cy, r, fill, cls='', style=''):
    k = r * .2
    d = (f'M{n(cx)} {n(cy - r)}Q{n(cx + k)} {n(cy - k)} {n(cx + r)} {n(cy)}Q{n(cx + k)} {n(cy + k)} {n(cx)} {n(cy + r)}'
         f'Q{n(cx - k)} {n(cy + k)} {n(cx - r)} {n(cy)}Q{n(cx - k)} {n(cy - k)} {n(cx)} {n(cy - r)}Z')
    c = f' class="{cls}"' if cls else ''
    s = f' style="{style}"' if style else ''
    return f'<path d="{d}" fill="{fill}"{c}{s}/>'


def chip(x, y, text, slug=None, dot=None, glyph=None, size=CHIP, h=34, w=500, color=None,
         fill=None, stroke=None, pad=13, rx=None):
    cy = y + h / 2
    inner, iw = '', 0
    if slug:
        isz = size + 1.5
        inner, iw = icon(slug, x + pad, cy - isz / 2, isz), isz + 7
    elif glyph:
        inner, iw = glyph(x + pad + 7, cy), 14 + 7
    elif dot:
        inner, iw = f'<rect x="{n(x + pad)}" y="{n(cy - 3)}" width="6" height="6" rx="1.5" fill="{dot}"/>', 6 + 8
    width = pad + iw + tw(text, 's', size, w) + pad
    svg = (f'<rect x="{n(x)}" y="{n(y)}" width="{n(width)}" height="{h}" rx="{n(h / 2 if rx is None else rx)}" '
           f'fill="{fill or SURFACE}" stroke="{stroke or LINE2}"/>' + inner
           + T(x + pad + iw, cy + size * .35, text, 's', size, w, color or FG2))
    return svg, width


def chip_width(text, **kw):
    """Width of a chip without recording its glyphs."""
    saved = {k: set(v) for k, v in USED.items()}
    _, wd = chip(0, 0, text, **kw)
    for k in USED:
        USED[k] = saved[k]
    return wd


def chip_flow(x, y, maxw, items, gap=8, rowgap=8, **kw):
    h = kw.get('h', 34)
    cx, cy, out = x, y, []
    for text, extra in items:
        wd = chip_width(text, **extra, **kw)
        if cx > x and cx + wd > x + maxw:
            cx, cy = x, cy + h + rowgap
        svg, wd = chip(cx, cy, text, **extra, **kw)
        out.append(svg)
        cx += wd + gap
    return ''.join(out), cy + h


def tagged(pairs, dot=None):
    return [(t, {'slug': s} if s else {'dot': dot or VIOLET}) for t, s in pairs]


def label(x, y, idx, text, anchor='start'):
    parts = ([(idx + '  ', 'm', LABEL, 500, FG4, 1.8)] if idx else []) + [(text, 'm', LABEL, 500, FG3, 1.8)]
    return runs(x, y, parts, anchor)[0]


def heading(x, y, a, b, size=46):
    return runs(x, y, [(a, 's', size, 600, FG, -1.4), (b, 'i', size * 1.12, 400, 'url(#grad)')])[0]


def section_head(W, idx, name, a, b, meta):
    return (label(M, 40, idx, name) + heading(M, 98, a, b)
            + T(W - M, 98, meta, 'm', META, 500, FG3, 'end', ls=1.6)
            + f'<line x1="{M}" y1="132" x2="{W - M}" y2="132" stroke="{LINE}"/>')


def pulse_dot(cx, cy, r=4, color=None):
    color = color or GREEN
    return (f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{r}" fill="{color}" class="pulse"/>'
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{r}" fill="{color}"/>')


def pill(x, y, text, size=13.5, h=36, anchor='start'):
    wd = 38 + tw(text, 'm', size, 500, 1.6) + 14
    if anchor == 'middle':
        x -= wd / 2
    return (f'<rect x="{n(x)}" y="{n(y)}" width="{n(wd)}" height="{h}" rx="{h / 2}" fill="{GREEN_BG}" '
            f'stroke="{GREEN_STROKE}"/>' + pulse_dot(x + 21, y + h / 2)
            + T(x + 38, y + h / 2 + size * .36, text, 'm', size, 500, GREEN_TEXT, ls=1.6))


def grid(w, h, step, cx, cy, r, ident='g', dots=False, alpha=.05):
    cell = (f'<circle cx="{step / 2}" cy="{step / 2}" r="1.1" fill="{ink(alpha)}"/>' if dots else
            f'<path d="M{step} 0H0V{step}" fill="none" stroke="{ink(alpha)}"/>')
    defs = (f'<pattern id="{ident}p" width="{step}" height="{step}" patternUnits="userSpaceOnUse">{cell}</pattern>'
            f'<radialGradient id="{ident}r" cx="{cx}" cy="{cy}" r="{r}" gradientUnits="userSpaceOnUse">'
            '<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>'
            f'<mask id="{ident}m"><rect width="{w}" height="{h}" fill="url(#{ident}r)"/></mask>')
    return defs, f'<rect width="{w}" height="{h}" fill="url(#{ident}p)" mask="url(#{ident}m)"/>'


def glow(cx, cy, r, tint, opacity, cls=''):
    """Soft ambient light. Faded out at the card edges by doc() so it never shows a hard cut."""
    c = f' class="{cls}"' if cls else ''
    return f'<g{c}><circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#glow{tint})" opacity="{n(opacity * GLOW)}"/></g>'


def _gradient(ident, stops, x2='1', y2='0', x1='0', y1='0'):
    return (f'<linearGradient id="{ident}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
            f'<stop offset="0" stop-color="{stops[0]}"/><stop offset=".52" stop-color="{stops[1]}"/>'
            f'<stop offset="1" stop-color="{stops[2]}"/></linearGradient>')


def common_defs():
    return (_gradient('grad', GRAD) + _gradient('gradP', PASTEL)
            + f'<filter id="shadow" x="-30%" y="-30%" width="160%" height="190%"><feDropShadow dx="0" dy="10" '
              f'stdDeviation="12" flood-color="#000" flood-opacity="{SHADOW}"/></filter>'
            + ''.join(f'<radialGradient id="glow{k}"><stop offset="0" stop-color="{c}" stop-opacity=".55"/>'
                      f'<stop offset=".45" stop-color="{c}" stop-opacity=".16"/><stop offset="1" stop-color="{c}" '
                      f'stop-opacity="0"/></radialGradient>' for k, c in zip('BVP', PASTEL)))


BASE_CSS = (
    ".s{font-family:G,ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}"
    ".m{font-family:GM,ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}"
    ".i{font-family:IS,'Instrument Serif',Georgia,'Times New Roman',serif;font-style:italic}"
    ".pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.4s cubic-bezier(.2,.7,.2,1) infinite}"
    "@keyframes pulse{from{transform:scale(1);opacity:.7}to{transform:scale(3.4);opacity:0}}"
    ".blink{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
    ".bob{animation:bob 6s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-9px)}}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
)


def doc(w, h, body, css='', defs='', title='', glows=''):
    """A borderless, transparent card."""
    t = escape(title, {'"': '&quot;'})
    edge = (f'<radialGradient id="edgeR"><stop offset=".5" stop-color="#fff"/><stop offset="1" stop-color="#000"/>'
            f'</radialGradient><mask id="edge" maskUnits="userSpaceOnUse" x="0" y="0" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="url(#edgeR)"/></mask>') if glows else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" '
            f'height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{t}"><title>{escape(title)}</title>'
            f'<style>{font_css()}{BASE_CSS}{css}</style><defs>{common_defs()}{edge}{defs}</defs>'
            + (f'<g mask="url(#edge)">{glows}</g>' if glows else '') + f'{body}</svg>')


def save(name, svg):
    out = os.path.join(ASSETS, THEME)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, name), 'w') as fh:
        fh.write(svg)
    print(f'  assets/{THEME}/{name:<22} {len(svg) / 1024:6.1f} KB')


# ════════════════════════════════════════════════════════════════════════════
# HERO
# ════════════════════════════════════════════════════════════════════════════

PLANE = 'M8 0L-2 -7H-4.6L-1.2 -1.6H-6L-8 -4H-9.6L-8.4 0L-9.6 4H-8L-6 1.6H-1.2L-4.6 7H-2Z'
SHIRT = 'M-26 -30L-10 -36Q0 -28 10 -36L26 -30L36 -8L24 -2L22 40H-22L-24 -2L-36 -8Z'


def odometer(x, y, text, size, uid, delay):
    """Numbers that roll into place, digit by digit."""
    lh = size * 1.1
    cx, body, css = x, [], []
    for k, ch in enumerate(text):
        wd = tw(ch, 's', size, 600, -1)
        if ch.isdigit():
            d = int(ch)   # spins one full turn and lands back on d, so a still frame is correct
            seq = list(range(d, 10)) + list(range(d + 1))
            shift = (len(seq) - 1) * lh
            col = ''.join(T(cx, y + i * lh, str(d), 's', size, 600, FG, ls=-1) for i, d in enumerate(seq))
            cls = f'od{uid}{k}'
            css.append(f'.{cls}{{animation:{cls} {1.5 + .2 * k:.2f}s cubic-bezier(.2,.75,.15,1) {delay + .08 * k:.2f}s both}}'
                       f'@keyframes {cls}{{from{{transform:translateY(0)}}to{{transform:translateY(-{shift:.1f}px)}}}}')
            body.append(f'<g class="{cls}" transform="translate(0 -{shift:.1f})">{col}</g>')
        else:
            body.append(T(cx, y, ch, 's', size, 600, VIOLET if ch == '+' else FG, ls=-1))
        cx += wd
    clip = (f'<clipPath id="odc{uid}"><rect x="{n(x - 4)}" y="{n(y - size * .8)}" width="{n(cx - x + 8)}" '
            f'height="{n(size * .9)}"/></clipPath>')
    return clip, f'<g clip-path="url(#odc{uid})">{"".join(body)}</g>', ''.join(css)


def typing(x, y, cmds, size, slot=4.2, cps=22):
    """A terminal that types out commands one after another (SMIL, loops forever)."""
    cw = tw('a', 'm', size)
    total = slot * len(cmds)
    defs, body = [], []
    cur_pts = [(0, 0)]
    first = len(cmds[0]) * cw   # the first command starts fully typed, so a still frame shows it
    cur_pts = [(0, first)]
    for i, cmd in enumerate(cmds):
        t0, dt = i * slot + .35, 1 / cps
        typed = [] if i == 0 else [((t0 + c * dt) / total, c * cw) for c in range(1, len(cmd) + 1)]
        end = (((i + 1) * slot - .3) / total, 0)
        cur_pts += typed + [end]
        start = first if i == 0 else 0
        pts = [(0, start)] + typed + [end, (1, start)]
        kt = ';'.join(f'{p[0]:.4f}' for p in pts)
        vals = ';'.join(f'{p[1]:.1f}' for p in pts)
        defs.append(f'<clipPath id="ty{i}"><rect x="{n(x)}" y="{n(y - size)}" height="{n(size * 1.6)}" width="0">'
                    f'<animate attributeName="width" dur="{total}s" repeatCount="indefinite" calcMode="discrete" '
                    f'keyTimes="{kt}" values="{vals}"/></rect></clipPath>')
        body.append(f'<g clip-path="url(#ty{i})">{T(x, y, cmd, "m", size, 400, FG)}</g>')
    cur_pts.append((1, first))
    kt = ';'.join(f'{p[0]:.4f}' for p in cur_pts)
    vals = ';'.join(f'{x + p[1] + 2:.1f}' for p in cur_pts)
    body.append(f'<rect x="{n(x + first + 2)}" y="{n(y - size * .82)}" width="{n(cw * .62)}" height="{n(size * 1.05)}" rx="1.5" '
                f'fill="{VIOLET}" class="blink"><animate attributeName="x" dur="{total}s" repeatCount="indefinite" '
                f'calcMode="discrete" keyTimes="{kt}" values="{vals}"/></rect>')
    return ''.join(defs), ''.join(body)


def cta(SW, text, uid, glyph=False):
    y = 446
    g = sparkle(SW / 2 - tw(text, 's', 14, 600) / 2 - 10, y + 23, 6, '#0b0b0e') if glyph else ''
    tx = SW / 2 + (5 if glyph else 0)
    return (f'<clipPath id="cta{uid}"><rect x="14" y="{y}" width="{SW - 28}" height="46" rx="15"/></clipPath>'
            f'<rect x="14" y="{y}" width="{SW - 28}" height="46" rx="15" fill="url(#gradP)"/>{g}'
            + T(tx, y + 28, text, 's', 14, 600, '#0b0b0e', 'middle')
            + f'<g clip-path="url(#cta{uid})"><g class="shine"><rect x="-70" y="{y - 10}" width="34" height="66" '
              f'fill="rgba(255,255,255,.45)" transform="skewX(-22)"/></g></g>')


def screen_travel(SW):
    o = [T(20, 76, 'FLIGHTS · HOTELS', 'm', 10, 500, FG3, ls=1.4), T(20, 107, 'Where to next?', 'i', 29, 400, FG)]
    o.append(f'<g><rect x="14" y="124" width="{SW - 28}" height="118" rx="18" '
             f'fill="#141419" stroke="{LINE2}"/>')
    o.append(T(30, 164, 'PNQ', 's', 24, 600, FG, ls=-.5) + T(30, 182, 'Pune', 's', 11.5, 400, FG3))
    o.append(T(SW - 30, 164, 'DXB', 's', 24, 600, FG, 'end', ls=-.5) + T(SW - 30, 182, 'Dubai', 's', 11.5, 400, FG3, 'end'))
    o.append(f'<path id="arcA" d="M94 158Q124 124 154 158" fill="none" stroke="{FG4}" stroke-dasharray="2 4"/>')
    o.append(f'<g><path d="{PLANE}" fill="{VIOLET}" transform="scale(.85)"/><animateMotion dur="3.4s" '
             f'repeatCount="indefinite" rotate="auto"><mpath xlink:href="#arcA"/></animateMotion></g>')
    o.append(f'<line x1="30" y1="200" x2="{SW - 30}" y2="200" stroke="{LINE2}" stroke-dasharray="3 4"/>')
    o.append(T(30, 224, 'Wed, 14 Oct', 's', 11, 400, FG3) +
             T(SW - 30, 224, 'Non-stop · 3h 15m', 's', 11, 500, FG2, 'end') + '</g>')
    o.append(f'<circle cx="24" cy="266" r="3" fill="{GREEN}"/>' + T(33, 269.5, 'AI ASSISTANT · LIVE', 'm', 10, 500, FG3, ls=1.2))
    msg = 'Download my e-ticket'
    bw = tw(msg, 's', 12.5) + 26
    o.append(f'<g><rect x="{n(SW - 14 - bw)}" y="282" width="{n(bw)}" height="32" rx="14" '
             f'fill="rgba(180,162,255,.16)" stroke="rgba(180,162,255,.36)"/>'
             + T(SW - 14 - bw + 13, 302.5, msg, 's', 12.5, 400, FG) + '</g>')
    lines = ['Sent to your email. Want a', 'hotel near DXB too?']
    aw = max(tw(s, 's', 12.5) for s in lines) + 26
    o.append(f'<g><rect x="14" y="326" width="{n(aw)}" height="52" rx="14" fill="#1c1c24" stroke="{LINE}"/>'
             + T(27, 347, lines[0], 's', 12.5, 400, FG) + T(27, 365, lines[1], 's', 12.5, 400, FG) + '</g>')
    qx, q = 14, []
    for s in ('Show hotels', 'Not now'):
        svg, wd = chip(qx, 390, s, size=11.5, h=26, color=FG2, pad=11)
        q.append(svg)
        qx += wd + 6
    o.append(''.join(q))
    o.append(cta(SW, 'Continue to payment', 'A'))
    return ''.join(o)


def screen_tryon(SW):
    o = [T(20, 76, 'TRYWARE AI · VIRTUAL TRY-ON', 'm', 10, 500, FG3, ls=1.4), T(20, 107, 'Try it on.', 'i', 29, 400, FG),
         f'<rect x="14" y="124" width="{SW - 28}" height="228" rx="18" fill="url(#tryBg)" stroke="{LINE2}"/>']
    cx = SW / 2
    o.append(f'<circle cx="{cx}" cy="186" r="21" fill="#2b2935"/><rect x="{cx - 8}" y="200" width="16" height="16" fill="#2b2935"/>'
             f'<path d="M{cx - 60} 352C{cx - 58} 262 {cx - 40} 222 {cx} 216C{cx + 40} 222 {cx + 58} 262 {cx + 60} 352Z" fill="#24222d"/>')
    o.append(f'<clipPath id="revB"><rect x="14" y="214" width="{SW - 28}" height="140">'
             '<animate attributeName="height" dur="15s" repeatCount="indefinite" keyTimes="0;.36;.55;.7;1" '
             'values="0;0;140;140;0"/></rect></clipPath>')
    o.append(f'<g clip-path="url(#revB)"><path d="M{cx - 62} 352C{cx - 60} 262 {cx - 42} 220 {cx - 14} 214Q{cx} 232 {cx + 14} 214'
             f'C{cx + 42} 220 {cx + 60} 262 {cx + 62} 352Z" fill="url(#gradP)" opacity=".92"/>'
             f'<path d="M{cx - 14} 214Q{cx} 232 {cx + 14} 214" fill="none" stroke="rgba(8,8,10,.35)" stroke-width="2"/>'
             f'<path d="M{cx - 40} 300H{cx + 40}" stroke="rgba(8,8,10,.18)" stroke-width="1.5"/></g>')
    o.append(f'<g class="bB" opacity="0"><rect x="14" y="200" width="{SW - 28}" height="28" fill="url(#beam)"/>'
             f'<rect x="14" y="213" width="{SW - 28}" height="2" fill="url(#gradP)"/></g>')
    o.append(f'<rect x="26" y="136" width="34" height="22" rx="7" fill="rgba(0,0,0,.45)" stroke="{LINE2}"/>'
             + T(43, 151, 'HD', 'm', 10, 600, FG, 'middle'))
    for i, (sx, sy, r) in enumerate(((SW - 44, 154, 7), (52, 236, 5), (SW - 54, 300, 5.5))):
        o.append(sparkle(sx, sy, r, '#fff', 'spB', f'animation-delay:{i * .25}s'))
    o.append(f'<g class="gB">{T(20, 376, "Generating try-on…", "s", 12, 400, FG2)}</g>'
             f'<g class="rB" opacity="0">{T(20, 376, "Ready in HD", "s", 12, 500, FG)}</g>'
             + T(SW - 20, 376, 'gpt-image', 'm', 10, 500, FG3, 'end'))
    o.append(f'<rect x="20" y="386" width="{SW - 40}" height="5" rx="2.5" fill="#1f1f27"/>'
             f'<rect x="20" y="386" width="{SW - 40}" height="5" rx="2.5" fill="url(#gradP)" class="pB"/>')
    for i, c in enumerate((PINK, BLUE, FG3)):
        x = 20 + i * 72
        o.append(f'<rect x="{x}" y="402" width="64" height="34" rx="10" fill="#16161c" '
                 f'stroke="{"url(#gradP)" if i == 0 else LINE2}" stroke-width="{1.5 if i == 0 else 1}"/>'
                 f'<path d="{SHIRT}" transform="translate({x + 32} 419) scale(.3)" fill="{c}"/>')
    o.append(cta(SW, 'Generate in HD', 'B', glyph=True))
    return ''.join(o)


def screen_ride(SW, SH):
    o = [f'<rect width="{SW}" height="{SH}" fill="#0d0f13"/>',
         f'<path d="M-10 250C40 230 70 268 120 250S200 214 260 236" fill="none" stroke="rgba(142,197,255,.09)" stroke-width="16"/>',
         '<rect x="186" y="270" width="70" height="70" rx="16" fill="rgba(74,222,128,.06)"/>']
    o += [f'<path d="M{x} 0V{SH}" stroke="#181a21" stroke-width="10"/>' for x in (60, 170, 226)]
    o += [f'<path d="M0 {y}H{SW}" stroke="#181a21" stroke-width="10"/>' for y in (130, 190, 312, 400)]
    o += [f'<path d="M{x} 0V{SH}" stroke="#13151a" stroke-width="4"/>' for x in (20, 116, 198)]
    o.append('<path d="M0 60L248 160" stroke="#13151a" stroke-width="4"/>')
    route = 'M60 372V322Q60 312 70 312H160Q170 312 170 302V200Q170 190 180 190H226'
    o.append(f'<path d="{route}" fill="none" stroke="rgba(180,162,255,.22)" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>')
    o.append(f'<path id="routeC" d="{route}" pathLength="1" fill="none" stroke="url(#gradV)" stroke-width="4" '
             f'stroke-linecap="round" stroke-linejoin="round" class="rC"/>')
    o.append(f'<circle cx="60" cy="372" r="6" fill="{FG}" stroke="#0d0f13" stroke-width="3"/>' + pulse_dot(226, 190, 6, PINK))
    o.append(f'<g><rect x="-9" y="-5.5" width="18" height="11" rx="3.5" fill="{FG}"/><rect x="2" y="-4" width="4" height="8" rx="1" '
             f'fill="#0d0f13"/><animateMotion dur="15s" repeatCount="indefinite" rotate="auto" calcMode="linear" '
             f'keyPoints="0;0;1;1" keyTimes="0;.72;.95;1"><mpath xlink:href="#routeC"/></animateMotion></g>')
    o.append(f'<rect x="14" y="58" width="{SW - 28}" height="40" rx="14" fill="{GLASS}" stroke="{LINE2}"/>'
             f'<circle cx="32" cy="78" r="4" fill="{GREEN}"/>' + T(44, 82, 'Pickup · Hinjewadi Phase 1', 's', 12, 500, FG))
    o.append(f'<path d="M0 {SH}V394Q0 372 22 372H{SW - 22}Q{SW} 372 {SW} 394V{SH}Z" fill="#111116" stroke="{LINE2}"/>'
             f'<rect x="{SW / 2 - 18}" y="381" width="36" height="4" rx="2" fill="{FG4}"/>')
    o.append(T(20, 414, 'Driver arriving', 's', 16, 600, FG, ls=-.3))
    o.append(f'<rect x="{SW - 72}" y="399" width="52" height="22" rx="11" fill="rgba(74,222,128,.12)"/>'
             + T(SW - 46, 414, '3 min', 'm', 10.5, 600, GREEN, 'middle'))
    o.append(f'<circle cx="34" cy="448" r="14" fill="url(#gradP)"/>' + T(34, 452.5, 'R', 's', 12, 700, '#0b0b0e', 'middle')
             + T(56, 444, 'Rahul · 4.9 rating', 's', 12.5, 500, FG) + T(56, 461, 'MH 12 · White Swift', 's', 11, 400, FG3))
    o.append(f'<rect x="14" y="474" width="{SW - 28}" height="32" rx="12" fill="{SURFACE}" stroke="{LINE2}"/>'
             + T(SW / 2, 494.5, 'Share live trip', 's', 12.5, 500, FG, 'middle'))
    return ''.join(o)


def phone(px, py, pw=268, ph=548):
    """A phone that cycles through three app screens. It stays a dark device in both themes."""
    sx, sy, sw, sh = px + 10, py + 10, pw - 20, ph - 20
    defs = (f'<clipPath id="scr"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="37"/></clipPath>'
            '<linearGradient id="tryBg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#17161f"/>'
            '<stop offset="1" stop-color="#1f1b2c"/></linearGradient>'
            '<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b4a2ff" stop-opacity="0"/>'
            '<stop offset=".5" stop-color="#b4a2ff" stop-opacity=".45"/><stop offset="1" stop-color="#b4a2ff" stop-opacity="0"/></linearGradient>'
            + _gradient('gradV', PASTEL, x1='0', y1='1', x2='1', y2='0'))
    with theme('dark'):
        o = [f'<g filter="url(#shadow)"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="46" fill="#0c0c10"/></g>',
             f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="46" fill="#0c0c10" stroke="rgba(255,255,255,.18)" stroke-width="1.5"/>',
             f'<rect x="{px + 4}" y="{py + 4}" width="{pw - 8}" height="{ph - 8}" rx="42" fill="none" stroke="rgba(255,255,255,.05)"/>',
             f'<rect x="{px - 2.5}" y="{py + 118}" width="3" height="32" rx="1.5" fill="#202027"/>',
             f'<rect x="{px - 2.5}" y="{py + 166}" width="3" height="56" rx="1.5" fill="#202027"/>',
             f'<rect x="{px + pw - .5}" y="{py + 150}" width="3" height="78" rx="1.5" fill="#202027"/>',
             f'<g clip-path="url(#scr)"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" fill="#0b0b0f"/>',
             f'<g transform="translate({sx} {sy})">',
             f'<g class="scA">{screen_travel(sw)}</g>',
             f'<g class="scB" transform="translate(260 0)">{screen_tryon(sw)}</g>',
             f'<g class="scC" transform="translate(260 0)">{screen_ride(sw, sh)}</g>',
             T(30, 34, '9:41', 's', 14, 600, FG),
             ''.join(f'<rect x="{sw - 84 + i * 5}" y="{27 - i * 2}" width="3" height="{4 + i * 2}" rx="1" fill="{FG}"/>' for i in range(4)),
             f'<rect x="{sw - 56}" y="24" width="23" height="11" rx="3.5" fill="none" stroke="{FG2}"/>'
             f'<rect x="{sw - 54}" y="26" width="16" height="7" rx="2" fill="{FG}"/>'
             f'<rect x="{sw - 32}" y="27.5" width="1.6" height="4" rx=".8" fill="{FG2}"/>',
             '</g></g>',
             f'<rect x="{px + pw / 2 - 44}" y="{py + 20}" width="88" height="26" rx="13" fill="#000"/>',
             f'<circle cx="{px + pw / 2 + 28}" cy="{py + 33}" r="4" fill="#0b0f1d"/>',
             f'<rect x="{px + pw / 2 - 50}" y="{py + ph - 21}" width="100" height="4" rx="2" fill="rgba(255,255,255,.4)"/>']
    # Three app screens take turns every 5 s; each one plays its own little story while on screen.
    css = (
        ".scA,.scB,.scC{animation:15s cubic-bezier(.7,0,.25,1) infinite}"
        ".scA{animation-name:scA}.scB{animation-name:scB}.scC{animation-name:scC}"
        "@keyframes scA{0%,30%{transform:translateX(0)}33.33%{transform:translateX(-260px);animation-timing-function:steps(1,end)}"
        "33.34%,96.66%{transform:translateX(260px)}100%{transform:translateX(0)}}"
        "@keyframes scB{0%,30%{transform:translateX(260px)}33.33%,63.33%{transform:translateX(0)}"
        "66.66%{transform:translateX(-260px);animation-timing-function:steps(1,end)}66.67%,100%{transform:translateX(260px)}}"
        "@keyframes scC{0%,63.33%{transform:translateX(260px)}66.66%,96.66%{transform:translateX(0)}100%{transform:translateX(-260px)}}"
        ".bB,.gB,.rB,.pB,.spB{animation:15s infinite}"
        ".bB{animation-name:bB;animation-timing-function:linear}"
        "@keyframes bB{0%,36%{transform:translateY(0);opacity:0}37%{opacity:1}55%{transform:translateY(138px);opacity:1}57%,100%{transform:translateY(138px);opacity:0}}"
        ".gB{animation-name:gB}@keyframes gB{0%,55%{opacity:1}56.5%,100%{opacity:0}}"
        ".rB{animation-name:rB}@keyframes rB{0%,55%{opacity:0}56.5%,100%{opacity:1}}"
        ".pB{transform-box:fill-box;transform-origin:0 50%;animation-name:pB;animation-timing-function:linear}"
        "@keyframes pB{0%,36%{transform:scaleX(0)}55%,100%{transform:scaleX(1)}}"
        ".spB{transform-box:fill-box;transform-origin:center;animation-name:spB}"
        "@keyframes spB{0%,55%{opacity:0;transform:scale(.3) rotate(0)}59%,63%{opacity:1;transform:scale(1) rotate(45deg)}66%,100%{opacity:0}}"
        ".rC{stroke-dasharray:1;animation:rC 15s linear infinite}@keyframes rC{0%,68%{stroke-dashoffset:1}79%,100%{stroke-dashoffset:0}}"
        ".shine{animation:shine 3.6s cubic-bezier(.5,0,.3,1) infinite}@keyframes shine{0%{transform:translateX(0)}45%,100%{transform:translateX(360px)}}"
    )
    return defs, ''.join(o), css


def floating_chip(x, y, text, slug=None, glyph=None, dot=None, delay=0):
    svg, _ = chip(x, y, text, slug=slug, glyph=glyph, dot=dot, size=15, h=42, color=FG, fill=GLASS,
                  stroke=GLASS_STROKE, pad=15)
    return f'<g class="bob" style="animation-delay:{delay}s"><g filter="url(#shadow)">{svg}</g></g>'


def hero():
    W, H = 1200, 620
    defs, body, css = [], [], []
    glows = (glow(1000, 150, 460, 'V', .5, 'd1') + glow(1120, 560, 380, 'P', .32, 'd2')
             + glow(720, 450, 340, 'B', .24, 'd3'))
    css.append('.d1{animation:d1 18s ease-in-out infinite alternate}@keyframes d1{to{transform:translate(-70px,40px)}}'
               '.d2{animation:d2 22s ease-in-out infinite alternate}@keyframes d2{to{transform:translate(-90px,-40px)}}'
               '.d3{animation:d3 20s ease-in-out infinite alternate}@keyframes d3{to{transform:translate(70px,-50px)}}')
    gd, gb = grid(W, H, 56, 980, 300, 560)
    defs.append(gd)
    body.append(gb)

    ocx, ocy = 980, 300
    body.append(''.join(f'<circle cx="{ocx}" cy="{ocy}" r="{r}" fill="none" stroke="{ink(.1)}" '
                        f'stroke-dasharray="1 9" stroke-linecap="round" stroke-width="1.6"/>' for r in (238, 300))
                + f'<g class="orbit"><circle cx="{ocx + 238}" cy="{ocy}" r="4" fill="{BLUE}"/>'
                  f'<circle cx="{ocx - 300}" cy="{ocy}" r="3.5" fill="{PINK}"/><circle cx="{ocx}" cy="{ocy - 300}" r="3" fill="{VIOLET}"/></g>')
    css.append(f'.orbit{{transform-origin:{ocx}px {ocy}px;animation:orbit 48s linear infinite}}'
               '@keyframes orbit{to{transform:rotate(360deg)}}')

    # ── left column
    L, dy = M, -20
    body.append(f'<g>{pill(L, 64 + dy, "AVAILABLE FOR OPPORTUNITIES")}</g>')
    body.append(f'<g>{T(L, 146 + dy, EYEBROW, "m", 14.5, 500, FG3, ls=2)}</g>')
    name_w = tw(NAME_FIRST, 's', 104, 600, -4.5)
    body.append(f'<g>{T(L - 4, 252 + dy, NAME_FIRST, "s", 104, 600, FG, ls=-4.5)}'
                f'{T(L + name_w + 18, 252 + dy, NAME_LAST, "i", 118, 400, "url(#grad)")}</g>')
    (a1, b1), (a2, b2) = TAGLINE
    t1, _ = runs(L, 309 + dy, [(a1, 's', 34, 400, FG, -.6), (b1, 'i', 40, 400, FG)])
    t2, _ = runs(L, 352 + dy, [(a2, 's', 34, 400, FG2, -.6), (b2, 'i', 40, 400, 'url(#grad)')])
    body.append(f'<g>{t1}{t2}</g>')

    tdefs, tbody = typing(L + 46, 418 + dy, TERMINAL, 17.5)
    defs.append(tdefs)
    body.append(f'<g><rect x="{L}" y="{388 + dy}" width="500" height="48" rx="12" '
                f'fill="{SURFACE}" stroke="{LINE2}"/>' + T(L + 21, 418 + dy, '$', 'm', 17.5, 500, VIOLET)
                + tbody + '</g>')

    body.append(f'<line x1="{L}" y1="{472 + dy}" x2="{L + 618}" y2="{472 + dy}" stroke="{LINE}"/>')
    for i, (val, l1, l2) in enumerate(STATS):
        x = L + i * 158
        clip, num, ocss = odometer(x, 534 + dy, val, 46, i, .7 + i * .12)
        defs.append(clip)
        css.append(ocss)
        body.append(num + T(x, 565 + dy, l1, 'm', 13, 500, FG3, ls=1.2) + T(x, 584 + dy, l2, 'm', 13, 500, FG3, ls=1.2))

    # ── phone
    px, py = 846, 24
    pdefs, pbody, pcss = phone(px, py)
    defs.append(pdefs)
    css.append(pcss)
    body.append(f'<g>{pbody}</g>')
    words = [('TRAVEL', 'lA'), ('GENAI', 'lB'), ('MOBILITY', 'lC')]
    total = sum(tw(w, 'm', 12.5, 500, 2) for w, _ in words) + 2 * 34
    x = px + 134 - total / 2
    for i, (w, cls) in enumerate(words):
        body.append(T(x, 601, w, 'm', 12.5, 500, FG4, ls=2, cls=cls))
        x += tw(w, 'm', 12.5, 500, 2)
        if i < 2:
            body.append(f'<circle cx="{n(x + 15)}" cy="597" r="1.8" fill="{FG4}"/>')
            x += 34
    on, off = FG, FG4
    css.append('.lA,.lB,.lC{animation:15s infinite}.lA{animation-name:lA}.lB{animation-name:lB}.lC{animation-name:lC}'
               f'@keyframes lA{{0%,31%{{fill:{on}}}34%,97%{{fill:{off}}}100%{{fill:{on}}}}}'
               f'@keyframes lB{{0%,31%{{fill:{off}}}34%,64%{{fill:{on}}}67%,100%{{fill:{off}}}}}'
               f'@keyframes lC{{0%,64%{{fill:{off}}}67%,97%{{fill:{on}}}100%{{fill:{off}}}}}')

    body.append(floating_chip(742, 80, 'Flutter', slug='flutter', delay=0))
    body.append(floating_chip(1046, 112, 'WebSocket', dot=GREEN, delay=-2))
    body.append(floating_chip(718, 420, 'LLM · RAG', glyph=lambda cx, cy: sparkle(cx, cy, 7, VIOLET), delay=-4))
    body.append(floating_chip(1050, 528, 'Razorpay', slug='razorpay', delay=-1))

    title = ('Omkar Gharge, Flutter & GenAI Engineer in Pune, India. Mobile apps for millions, made smarter with AI. '
             '3.5+ years shipping Flutter, 1M+ downloads on one app, 4 apps live on the stores, 6 payment gateways.')
    save('hero.svg', doc(W, H, ''.join(body), ''.join(css), ''.join(defs), title, glows))


# ════════════════════════════════════════════════════════════════════════════
# ABOUT  — the IDE window
# ════════════════════════════════════════════════════════════════════════════

KW = {'class', 'extends', 'final', 'const', 'return', 'async', 'await', 'void', 'var', 'static', 'import'}
TOKEN = re.compile(r"(///.*$)|('(?:[^'\\]|\\.)*')|(@\w+)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)|(\s+)|(.)")


def dart_tokens(line):
    out = []
    for m in TOKEN.finditer(line):
        com, st, ann, num, ident, ws, punct = m.groups()
        if com:
            out.append((com, SYNTAX['comment']))
        elif st:
            out.append((st, PINK))
        elif ann or num:
            out.append((ann or num, AMBER))
        elif ident:
            rest = line[m.end():]
            if ident in KW:
                c = VIOLET
            elif ident[0].isupper():
                c = BLUE
            elif rest.startswith('('):
                c = SYNTAX['fn']
            elif rest.startswith(':'):
                c = SYNTAX['named']
            else:
                c = SYNTAX['ident']
            out.append((ident, c))
        elif ws:
            out.append((ws, None))
        else:
            out.append((punct, FG3))
    return out


def about():
    W = 1200
    lines = CODE.split('\n')
    LH, top, size = 29, 100, 19
    cw = tw('a', 'm', size)
    bar = 42
    H = top + (len(lines) - 1) * LH + 32 + bar
    b, css = [], []
    win = f'M1 20Q1 1 20 1H{W - 20}Q{W - 1} 1 {W - 1} 20V{H - 20}Q{W - 1} {H - 1} {W - 20} {H - 1}H20Q1 {H - 1} 1 {H - 20}Z'
    b.append(f'<path d="{win}" fill="{WINDOW}" stroke="{LINE2}"/>')
    b.append(f'<line x1="1" y1="52" x2="{W - 1}" y2="52" stroke="{LINE}"/>')
    b.append(''.join(f'<circle cx="{28 + i * 21}" cy="26" r="6.5" fill="{c}"/>' for i, c in enumerate(('#ff5f57', '#febc2e', '#28c840'))))
    x = 102
    for i, (slug, name) in enumerate((('dart', 'omkar_gharge.dart'), ('python', 'tryware_api.py'),
                                      ('flutter', 'performance_guard.dart'))):
        wd = 16 + 16 + 9 + tw(name, 's', 14.5, 500) + 18
        if i == 0:
            b.append(f'<path d="M{x} 52V15Q{x} 9 {x + 6} 9H{n(x + wd - 6)}Q{n(x + wd)} 9 {n(x + wd)} 15V52" fill="{SURFACE}" stroke="{LINE}"/>'
                     f'<rect x="{x + 6}" y="9" width="{n(wd - 12)}" height="1.5" fill="url(#grad)"/>')
        b.append(icon(slug, x + 16, 23, 16, None if i == 0 else FG4) + T(x + 41, 36, name, 's', 14.5, 500, FG if i == 0 else FG3))
        x += wd + 4
    b.append(f'<g transform="translate({W - 100} 17)" fill="none" stroke="{FG3}" stroke-width="1.5"><circle cx="3" cy="3" r="2.5"/>'
             f'<circle cx="3" cy="15" r="2.5"/><circle cx="13" cy="5" r="2.5"/><path d="M3 5.5V12.5M13 7.5Q13 12 5.5 13.5"/></g>'
             + T(W - 78, 32, 'main', 'm', 14, 500, FG3))
    stagger, start = .085, .35
    last = len(lines) - 1
    b.append(f'<g class="cl" transform="translate(0 {last * LH})"><rect x="1" y="{top - 21}" width="1096" height="{LH}" '
             f'fill="{HILITE}"/><rect x="1" y="{top - 21}" width="2.5" height="{LH}" fill="{VIOLET}"/></g>')
    css.append(f'.cl{{animation:cl {last * stagger:.2f}s steps({last},end) {start:.2f}s both}}'
               f'@keyframes cl{{from{{transform:translateY(0)}}to{{transform:translateY({last * LH}px)}}}}')
    mini = []
    for i, line in enumerate(lines):
        y = top + i * LH
        indent = len(line) - len(line.lstrip(' '))
        spans, col = [], indent
        for tok, c in dart_tokens(line.lstrip(' ')):
            use('m', tok)
            if c:
                spans.append(f'<tspan fill="{c}">{escape(tok)}</tspan>')
                mini.append(f'<rect x="{n(1112 + col * .6)}" y="{n(74 + i * 4.4)}" width="{n(len(tok) * .6)}" height="2.3" '
                            f'rx="1" fill="{c}" opacity=".6"/>')
            else:
                spans.append(escape(tok))
            col += len(tok)
        code = (f'<text x="{n(96 + indent * cw)}" y="{y}" class="m" font-size="{size}" xml:space="preserve">'
                f'{"".join(spans)}</text>') if line else ''
        b.append(f'<g>'
                 + T(68, y, str(i + 1), 'm', 15, 400, FG4, 'end') + code + '</g>')
    end_x = 96 + len(lines[-1]) * cw + 3
    b.append(f'<rect x="{n(end_x)}" y="{top + last * LH - 17}" width="{n(cw * .7)}" height="23" rx="1.5" fill="{VIOLET}" class="blink"/>')
    b.append(f'<line x1="1098" y1="52" x2="1098" y2="{H - bar}" stroke="{LINE}"/>'
             f'<rect x="1104" y="66" width="84" height="{n(len(lines) * 4.4 + 14)}" rx="4" fill="{SURFACE}"/>'
             + ''.join(mini))
    sy = H - bar
    b.append(f'<line x1="1" y1="{sy}" x2="{W - 1}" y2="{sy}" stroke="{LINE}"/>'
             f'<circle cx="28" cy="{sy + 21}" r="7" fill="{GREEN_BG}"/><path d="M24.8 {sy + 21}l2.2 2.2 4.3-4.3" '
             f'fill="none" stroke="{GREEN}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')
    t, _ = runs(46, sy + 26, [('flutter analyze   ', 'm', 13.5, 500, FG2), ('No issues found!', 'm', 13.5, 500, GREEN)])
    b.append(t + T(W - 24, sy + 26, f'Dart  ·  UTF-8  ·  LF  ·  Ln {len(lines)}, Col 2', 'm', 13.5, 400, FG3, 'end'))
    title = ('About Omkar, written as a Dart class: Flutter & GenAI Engineer based in Pune, India with 3.5 years shipping. '
             'Shipped Akbar Travels (flights and hotels, 1M+ downloads, iOS + Android), TryWare AI (GenAI virtual try-on, '
             'built solo) and Buggy (ride-hailing rider + driver apps). Stack: Flutter, Dart, Swift, GetX, Riverpod, Bloc; '
             'LangChain, LangGraph, RAG, AI agents, OpenAI; FastAPI, Firebase, Supabase, WebSocket, Docker; Razorpay, PhonePe, '
             'Apple Pay, Tabby, Tamara.')
    save('about.svg', doc(W, H, ''.join(b), ''.join(css), '', title))


# ════════════════════════════════════════════════════════════════════════════
# EXPERIENCE
# ════════════════════════════════════════════════════════════════════════════

def experience():
    W = 1200
    tx, nx = M + 52, M + 14   # text column, timeline column
    b = [section_head(W, '01', 'EXPERIENCE', 'Shipping for ', 'real users.', '3.5+ YEARS  ·  2 COMPANIES  ·  4 APPS LIVE')]
    y, nodes, entries = 190, [], []
    for k, e in enumerate(EXPERIENCE):
        g = []
        nodes.append(y - 5)
        if e['current']:
            g.append(pulse_dot(nx, y - 5, 7, GREEN))
        else:
            g.append(f'<circle cx="{nx}" cy="{y - 5}" r="6.5" fill="none" stroke="{FG4 if e.get("education") else VIOLET}" stroke-width="2"/>')
        g.append(T(tx, y, e['period'], 'm', 14, 500, FG3, ls=1.6))
        if e['current']:
            px = tx + tw(e['period'], 'm', 14, 500, 1.6) + 12
            g.append(f'<rect x="{n(px)}" y="{y - 16.5}" width="52" height="23" rx="11.5" fill="{GREEN_BG}" stroke="{GREEN_STROKE}"/>'
                     + T(px + 26, y - .5, 'NOW', 'm', 11.5, 600, GREEN_TEXT, 'middle', ls=1.2))
        if e.get('education'):
            g.append(T(tx, y + 40, e['role'], 's', 27, 600, FG, ls=-.6) + T(tx, y + 72, e['points'][0], 's', BODY, 400, FG2))
            step = 0
        else:
            t, _ = runs(tx, y + 40, [(e['role'], 's', 27, 600, FG, -.6), ('  @ ' + e['company'], 's', 27, 400, FG2, -.6),
                                     ('  ' + e['detail'], 'i', 29, 400, 'url(#grad)')])
            g.append(t)
            for j, p in enumerate(e['points']):
                py = y + 78 + j * 31
                g.append(f'<rect x="{tx}" y="{py - 6.5}" width="11" height="1.8" rx=".9" fill="url(#grad)"/>'
                         + T(tx + 24, py, p, 's', BODY, 400, FG2))
            step = 78 + len(e['points']) * 31 + 40
        entries.append(f'<g>{"".join(g)}</g>')
        y += step
    # timeline segments stop short of each node, so hollow nodes stay hollow on any background
    segs = ''.join(f'M{nx} {a + 13}V{b_ - 13}' for a, b_ in zip(nodes, nodes[1:]))
    b.append(f'<path d="{segs}" stroke="url(#tl)" stroke-width="2" fill="none"/>')
    b += entries
    H = nodes[-1] + 5 + 72 + 24
    defs = (f'<linearGradient id="tl" x1="0" y1="{nodes[0]}" x2="0" y2="{nodes[-1]}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{GREEN}"/><stop offset=".35" stop-color="{VIOLET}"/><stop offset="1" stop-color="{FG4}"/></linearGradient>')
    title = ('Experience. Flutter Developer at Benzy Infotech (Akbar Travels Group), Jan 2025 to present: builds Akbar Travels, '
             '1M+ downloads, real-time AI support chatbot over WebSocket, Razorpay/Tamara/Tabby, CleverTap. Flutter Developer at '
             'Movilidad Technologies, Jun 2023 to Dec 2024: built Buggy rider and Buggy Sarathi driver apps from scratch, live maps, '
             'WebSocket sync. B.Tech Computer Science, DBATU, 2019 to 2023, CGPA 8.47.')
    save('experience.svg', doc(W, int(H), ''.join(b), '', defs, title, glow(1150, 20, 420, 'V', .2)))


# ════════════════════════════════════════════════════════════════════════════
# SELECTED WORK
# ════════════════════════════════════════════════════════════════════════════

def project_head(x, y, idx, cat, name, tagline, maxw, name_size=46, tag_size=30):
    ns = fit(name, 's', name_size, 600, maxw, -1.4)
    return (label(x, y, idx, cat) + T(x - 2, y + 58, name, 's', ns, 600, FG, ls=-1.4)
            + T(x, y + 98, tagline, 'i', fit(tagline, 'i', tag_size, 400, maxw), 400, 'url(#grad)'))


def bullets(x, y, items, maxw, size=18, lh=27):
    out = []
    for p in items:
        for j, line in enumerate(wrap(p, 's', size, 400, maxw - 24)):
            if j == 0:
                out.append(f'<rect x="{x}" y="{y - 6}" width="11" height="1.8" rx=".9" fill="url(#grad)"/>')
            out.append(T(x + 24, y, line, 's', size, 400, FG2))
            y += lh
        y += 7
    return ''.join(out), y


def work_akbar():
    W = 1200
    b, css, defs = [], [], []
    b.append(section_head(W, '02', 'SELECTED WORK', 'Things I’ve ', 'shipped.', '4 APPS LIVE ON THE STORES'))
    top = 192
    b.append(f'<g>{project_head(M, top, "01", "TRAVEL  ·  PRODUCTION  ·  2025 — NOW", "Akbar Travels", "Flights & hotels for a million-plus travellers.", 580, 54, 32)}</g>')
    summary = ('One of India’s leading travel-booking apps. I build and maintain it in Flutter for iOS and Android: '
               'flights, hotels, visa services and holiday packages, plus a real-time AI support chat.')
    sl = wrap(summary, 's', BODY + .5, 400, 580)
    b.append(f'<g>'
             + ''.join(T(M, top + 152 + i * 30, ln, 's', BODY + .5, 400, FG2) for i, ln in enumerate(sl)) + '</g>')
    my = top + 152 + len(sl) * 30 + 52
    mx, m = M, []
    for val, lab in (('1M+', 'DOWNLOADS'), ('2', 'PLATFORMS, ONE CODEBASE'), ('3', 'PAYMENT GATEWAYS')):
        m.append(T(mx, my, val, 's', 42, 600, FG, ls=-1.2) + T(mx, my + 27, lab, 'm', 12.5, 500, FG3, ls=1.3))
        mx += max(tw(lab, 'm', 12.5, 500, 1.3), tw(val, 's', 42, 600)) + 40
    b.append(f'<g>{"".join(m)}</g>')
    items = tagged((('Flutter', 'flutter'), ('GetX', None), ('WebSocket', None), ('CleverTap', None), ('Hive', None),
                    ('Razorpay', 'razorpay'), ('Tamara', None), ('Tabby', None), ('App Store', 'apple'), ('Google Play', 'googleplay')))
    cf, bottom = chip_flow(M, my + 64, W - 2 * M, items)
    b.append(f'<g>{cf}</g>')
    H = int(bottom + 12)

    # route network
    X0, Y0 = 640, top - 12
    PW, PH = W - M - X0, my + 34 - Y0
    sx, sy = PW / 484, PH / 300
    gd, gb = grid(W, H, 15, X0 + PW * .6, Y0 + PH / 2, 320, 'rt', dots=True, alpha=.13)
    defs.append(gd + f'<clipPath id="rtc"><rect x="{X0}" y="{Y0}" width="{n(PW)}" height="{n(PH)}" rx="20"/></clipPath>'
                f'<linearGradient id="arc" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{VIOLET}"/>'
                f'<stop offset="1" stop-color="{BLUE}" stop-opacity=".9"/></linearGradient>')
    v = [f'<rect x="{X0}" y="{Y0}" width="{n(PW)}" height="{n(PH)}" rx="20" fill="{SURFACE}" stroke="{LINE}"/>',
         f'<g clip-path="url(#rtc)">{gb}</g>', T(X0 + 24, Y0 + 36, 'ROUTE NETWORK', 'm', 12, 500, FG4, ls=1.8)]
    hub = (X0 + 312 * sx, Y0 + 168 * sy)
    cities = [('LHR', 58, 80), ('JED', 108, 214), ('DXB', 192, 140), ('DEL', 346, 78), ('BLR', 356, 248),
              ('BKK', 440, 150), ('SIN', 432, 262)]
    for i, (code, cx, cy) in enumerate(cities):
        cx, cy = X0 + cx * sx, Y0 + cy * sy
        dx, dy = cx - hub[0], cy - hub[1]
        dist = math.hypot(dx, dy)
        nx, ny = -dy / dist, dx / dist
        if ny > 0:
            nx, ny = -nx, -ny
        ctrl = ((hub[0] + cx) / 2 + nx * dist * .28, (hub[1] + cy) / 2 + ny * dist * .28)
        d = f'M{n(hub[0])} {n(hub[1])}Q{n(ctrl[0])} {n(ctrl[1])} {n(cx)} {n(cy)}'
        v.append(f'<path id="r{i}" d="{d}" fill="none" stroke="url(#arc)" stroke-width="1.6" stroke-opacity=".8"/>')
        below = cy > hub[1] - 10
        v.append(f'<circle cx="{n(cx)}" cy="{n(cy)}" r="4" fill="{FG}"/>'
                 + T(cx, cy + (22 if below else -13), code, 'm', 13, 500, FG2, 'middle', ls=1))
        if i in (0, 2, 4, 6):
            dur, beg = f'{2.6 + i * .3:.1f}s', f'{1.6 + i * .2:.1f}s'
            v.append(f'<circle r="2.8" fill="{FG}" opacity="0"><animateMotion dur="{dur}" begin="{beg}" repeatCount="indefinite" '
                     f'keyPoints="0;1;1" keyTimes="0;.8;1" calcMode="linear"><mpath xlink:href="#r{i}"/></animateMotion>'
                     f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.1;.75;1" dur="{dur}" begin="{beg}" '
                     f'repeatCount="indefinite"/></circle>')
    v.append(pulse_dot(hub[0], hub[1], 6, VIOLET) + T(hub[0] + 14, hub[1] + 24, 'PNQ', 'm', 14, 600, FG, ls=1))
    tx, ty = X0 + 24, Y0 + PH - 84
    v.append(f'<g class="toast"><g filter="url(#shadow)"><rect x="{tx}" y="{n(ty)}" width="262" height="60" rx="15" fill="{GLASS}" '
             f'stroke="{GLASS_STROKE}"/></g><circle cx="{tx + 26}" cy="{n(ty + 30)}" r="11" fill="{GREEN_BG}"/>'
             f'<path d="M{tx + 21} {n(ty + 30)}l3.4 3.4 6-6" fill="none" stroke="{GREEN}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
             + T(tx + 48, ty + 26, 'Booking confirmed', 's', 15, 600, FG) + T(tx + 48, ty + 45, 'PNQ – DXB · e-ticket sent', 's', 13, 400, FG3)
             + '</g>')
    css.append('.toast{animation:toast 7s cubic-bezier(.2,.7,.2,1) infinite 2.4s}'
               '@keyframes toast{0%{opacity:0;transform:translateY(10px)}8%,70%{opacity:1;transform:none}80%,100%{opacity:0;transform:translateY(-4px)}}')
    b.append(''.join(v))
    title = ('Selected work, 01: Akbar Travels, flights and hotels app with 1M+ downloads, built and maintained in Flutter for '
             'iOS and Android with a real-time AI support chat. Stack: Flutter, GetX, WebSocket, CleverTap, Hive, Razorpay, '
             'Tamara, Tabby. On the App Store and Google Play.')
    glows = glow(960, 340, 420, 'V', .22) + glow(1150, 60, 300, 'B', .16)
    save('work-akbar.svg', doc(W, H, ''.join(b), ''.join(css), ''.join(defs), title, glows))


def node(x, y, text, slug=None, glyph=None, h=46, size=15):
    return chip(x, y, text, slug=slug, glyph=glyph, size=size, h=h, color=FG, fill=NODE, stroke=LINE2, pad=14, rx=12)


def node_width(text, slug=None, glyph=None, h=46, size=15):
    return chip_width(text, slug=slug, glyph=glyph, size=size, h=h, pad=14)


def tryware_visual(X, Y, PW, PH):
    o = [f'<rect x="{X}" y="{Y}" width="{PW}" height="{PH}" rx="18" fill="{SURFACE}" stroke="{LINE}"/>',
         T(X + PW - 18, Y + 26, 'ARCHITECTURE', 'm', 11.5, 500, FG4, 'end', ls=1.6)]
    top = [('Flutter app', 'flutter', None), ('FastAPI', 'fastapi', None),
           ('gpt-image', None, lambda cx, cy: sparkle(cx, cy, 7, VIOLET))]
    widths = [node_width(t, s, g) for t, s, g in top]
    gap = (PW - 40 - sum(widths)) / 2
    x, ny, edges = X + 20, Y + 42, []
    for (t, s, g), wd in zip(top, widths):
        o.append(node(x, ny, t, s, g)[0])
        edges.append((x, x + wd))
        x += wd + gap
    for i in range(2):
        x1, x2, cy = edges[i][1], edges[i + 1][0], ny + 23
        o.append(f'<path id="tw{i}" d="M{n(x1)} {cy}H{n(x2)}" stroke="{LINE2}" stroke-width="1.5" stroke-dasharray="3 4"/>')
        for k in range(2):
            b0 = f'{k * .9 + i * .3:.1f}s'
            o.append(f'<circle r="3.2" fill="{VIOLET if k == 0 else PINK}" opacity="0"><set attributeName="opacity" to="1" begin="{b0}"/>'
                     f'<animateMotion dur="1.8s" begin="{b0}" repeatCount="indefinite"><mpath xlink:href="#tw{i}"/></animateMotion></circle>')
    sub = [('Firebase Auth', 'firebase', None), ('Razorpay hooks', 'razorpay', None),
           ('Row-lock credits', None, lambda cx, cy: f'<rect x="{n(cx - 4)}" y="{n(cy - 4)}" width="8" height="8" rx="2" fill="{AMBER}"/>')]
    sw = [node_width(t, s, g, 38, 14) for t, s, g in sub]
    sgap = (PW - 40 - sum(sw)) / 2
    sx, sy = X + 20, Y + 132
    api_c = sum(edges[1]) / 2
    o.append(f'<path d="M{n(api_c)} {ny + 46}V{sy - 14}" stroke="{LINE2}" stroke-width="1.5"/>')
    mids = []
    for (t, s, g), wd in zip(sub, sw):
        o.append(node(sx, sy, t, s, g, 38, 14)[0] + f'<path d="M{n(sx + wd / 2)} {sy - 14}V{sy}" stroke="{LINE2}" stroke-width="1.5"/>')
        mids.append(sx + wd / 2)
        sx += wd + sgap
    o.append(f'<path d="M{n(mids[0])} {sy - 14}H{n(mids[-1])}" stroke="{LINE2}" stroke-width="1.5"/>')
    o.append(f'<circle r="3.2" fill="{AMBER}"><animateMotion dur="2.4s" repeatCount="indefinite" '
             f'path="M{n(api_c)} {ny + 46}V{sy - 14}H{n(mids[-1])}V{sy}"/></circle>')
    o.append(T(X + PW / 2, Y + PH - 16, 'DOCKER · CADDY AUTO-HTTPS · GITHUB ACTIONS · HETZNER VPS', 'm', 11.5, 500, FG3, 'middle', ls=1))
    return ''.join(o)


def buggy_visual(X, Y, PW, PH):
    """A dark map panel (it stays a map UI in both themes)."""
    with theme('dark'):
        o = [f'<clipPath id="mapc"><rect x="{X}" y="{Y}" width="{PW}" height="{PH}" rx="18"/></clipPath>',
             f'<g clip-path="url(#mapc)"><rect x="{X}" y="{Y}" width="{PW}" height="{PH}" fill="#0d0f13"/>',
             f'<path d="M{X} {Y + 150}C{X + 80} {Y + 120} {X + 140} {Y + 190} {X + 230} {Y + 160}S{X + 330} {Y + 120} {X + 380} {Y + 140}" '
             f'fill="none" stroke="rgba(142,197,255,.08)" stroke-width="18"/>',
             f'<rect x="{X + 210}" y="{Y + 18}" width="80" height="54" rx="12" fill="rgba(74,222,128,.06)"/>']
        o += [f'<path d="M{X + xx} {Y}V{Y + PH}" stroke="#181a21" stroke-width="9"/>' for xx in (50, 140, 250, 330)]
        o += [f'<path d="M{X} {Y + yy}H{X + PW}" stroke="#181a21" stroke-width="9"/>' for yy in (40, 104, 176)]
        o += [f'<path d="M{X + xx} {Y}V{Y + PH}" stroke="#13151a" stroke-width="3.5"/>' for xx in (95, 200, 290)]
        route = (f'M{X + 50} {Y + 176}V{Y + 114}Q{X + 50} {Y + 104} {X + 60} {Y + 104}H{X + 130}Q{X + 140} {Y + 104} {X + 140} {Y + 94}'
                 f'V{Y + 50}Q{X + 140} {Y + 40} {X + 150} {Y + 40}H{X + 250}')
        o.append(f'<path d="{route}" fill="none" stroke="rgba(180,162,255,.2)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>')
        o.append(f'<path id="bgr" d="{route}" fill="none" stroke="url(#gradP)" stroke-width="3.5" stroke-linecap="round" '
                 f'stroke-linejoin="round"/>')
        o.append(f'<circle cx="{X + 50}" cy="{Y + 176}" r="5.5" fill="{FG}" stroke="#0d0f13" stroke-width="3"/>' + pulse_dot(X + 250, Y + 40, 5.5, PINK))
        o.append(f'<g opacity="0"><set attributeName="opacity" to="1" begin="1s"/><rect x="-9" y="-5.5" width="18" height="11" rx="3.5" fill="{FG}"/>'
                 f'<rect x="2" y="-4" width="4" height="8" rx="1" fill="#0d0f13"/><animateMotion dur="6s" begin="1s" repeatCount="indefinite" '
                 f'rotate="auto" keyPoints="0;1;1" keyTimes="0;.82;1" calcMode="linear"><mpath xlink:href="#bgr"/></animateMotion></g>')
        stats = [('+30%', 'route accuracy', GREEN), ('−40%', 'response time', BLUE), ('+25%', 'driver response', GREEN)]
        ch = (PH - 16 * 2 - 2 * 8) / 3
        cx = X + PW - 180
        for i, (val, lab, c) in enumerate(stats):
            cy = Y + 16 + i * (ch + 8)
            o.append(f'<g><rect x="{n(cx)}" y="{n(cy)}" width="164" height="{n(ch)}" rx="12" '
                     f'fill="{GLASS}" stroke="{LINE2}"/><rect x="{n(cx)}" y="{n(cy + 12)}" width="2.5" height="{n(ch - 24)}" rx="1.2" fill="{c}"/>'
                     + T(cx + 16, cy + ch / 2 - 1, val, 's', 22, 600, FG, ls=-.6) + T(cx + 16, cy + ch / 2 + 17, lab, 's', 13.5, 400, FG3)
                     + '</g>')
        o.append('</g>')
        o.append(f'<rect x="{X}" y="{Y}" width="{PW}" height="{PH}" rx="18" fill="none" stroke="rgba(255,255,255,.1)"/>')
    return ''.join(o)


def half_card(idx, cat, title_, tagline, visual, points, chips):
    """Returns (body, height). Visual panel sits under the title; bullets and chips below."""
    hm, pw = 12, 576
    b = [f'<g>{project_head(hm, 40, idx, cat, title_, tagline, pw, 46, 30)}</g>',
         visual(hm, 176, pw, 214)]
    bl, y = bullets(hm, 438, points, pw)
    b.append(f'<g>{bl}</g>')
    cf, bottom = chip_flow(hm, y + 4, pw, chips, gap=7, rowgap=7)
    b.append(f'<g>{cf}</g>')
    return ''.join(b), int(bottom + 12)


def work_halves():
    cards = [
        ('work-tryware.svg', ('02', 'GENERATIVE AI  ·  SOLO BUILD', 'TryWare AI', 'Virtual try-on, idea to Play Store.',
                              tryware_visual,
                              ['Image pipeline on OpenAI gpt-image, picked over Gemini after testing face accuracy and cost.',
                               'Race-safe credits with row-level locking, Firebase Auth and Razorpay webhooks for credit packs.'],
                              tagged((('Flutter', 'flutter'), ('FastAPI', 'fastapi'), ('Python', 'python'), ('OpenAI', None),
                                      ('Firebase', 'firebase'), ('Razorpay', 'razorpay'), ('Docker', 'docker'),
                                      ('GitHub Actions', 'githubactions')))),
         'Selected work, 02: TryWare AI, a generative-AI virtual try-on app built solo from idea to Google Play. Flutter app, '
         'Python FastAPI backend, OpenAI gpt-image, Firebase Auth, Razorpay webhooks, row-locked credits, Docker, Caddy and '
         'GitHub Actions on a Hetzner VPS.'),
        ('work-buggy.svg', ('03', 'MOBILITY  ·  2023 — 2024', 'Buggy & Buggy Sarathi', 'Rider + driver apps, from scratch.',
                            buggy_visual,
                            ['Live tracking with Google Maps, Places API and battery-efficient background location.',
                             'WebSocket ride requests and driver allocation, a floating app bubble and audio ride alerts.'],
                            tagged((('Flutter', 'flutter'), ('Google Maps', 'googlemaps'), ('Places API', 'googlemaps'),
                                    ('WebSocket', None), ('Firebase', 'firebase'), ('AWS S3', None), ('Background location', None)))),
         'Selected work, 03: Buggy and Buggy Sarathi, a ride-hailing platform with rider and driver apps built from scratch. '
         'Route accuracy up 30%, response time down 40%, driver response up 25%. Google Maps, Places API, WebSocket, Firebase, AWS S3.'),
    ]
    built = []
    for name, args, alt in cards:
        body, h = half_card(*args)
        built.append((name, body, h, alt, font_css()))   # fonts captured per card
    H = max(h for _, _, h, _, _ in built)   # equal heights so the pair sits side by side
    for name, body, _, alt, fonts in built:
        svg = doc(600, H, body, '', '', alt)
        save(name, svg.replace('<style>', '<style>' + fonts, 1))


def work_perf():
    W, H = 1200, 300
    b = [label(M, 40, '04', 'OPEN SOURCE  ·  FLUTTER PACKAGE'),
         T(M - 2, 98, 'performance_guard', 'm', 40, 500, FG, ls=-1.2),
         T(M, 140, 'See jank before your users do.', 'i', 31, 400, 'url(#grad)')]
    desc = 'A debug-only Flutter widget that overlays rebuild counts, frame drops and memory usage in-app, with zero cost in release mode.'
    b.append(''.join(T(M, 182 + i * 28, ln, 's', 18.5, 400, FG2) for i, ln in enumerate(wrap(desc, 's', 18.5, 400, 660))))
    cf, _ = chip_flow(M, 240, 680, tagged((('Dart', 'dart'), ('Flutter', 'flutter'), ('Debug overlay', None)))
                      + [('No-op in release', {'dot': GREEN})], gap=7)
    b.append(cf)
    PW, PH = 400, 268
    X, Y = W - M - PW, 16
    with theme('dark'):   # the overlay is an in-app UI, dark in both themes
        o = [f'<g filter="url(#shadow)"><rect x="{X}" y="{Y}" width="{PW}" height="{PH}" rx="16" fill="{GLASS}" stroke="{LINE2}"/></g>',
             pulse_dot(X + 22, Y + 26, 3.5, GREEN), T(X + 34, Y + 30.5, 'PERFORMANCE GUARD', 'm', 12, 500, FG3, ls=1.4),
             f'<rect x="{X + PW - 70}" y="{Y + 13}" width="54" height="24" rx="7" fill="rgba(252,217,168,.1)" stroke="rgba(252,217,168,.3)"/>',
             T(X + PW - 43, Y + 29.5, 'DEBUG', 'm', 11, 600, AMBER, 'middle', ls=1),
             T(X + 20, Y + 90, '60', 's', 46, 600, FG, ls=-1.6), T(X + 78, Y + 90, 'FPS', 'm', 12.5, 500, FG3, ls=1)]
        for i, (lab, val) in enumerate((('REBUILDS', '128'), ('DROPPED', '2'), ('MEMORY', '142 MB'))):
            cx = X + 146 + i * 84
            o.append(T(cx, Y + 66, lab, 'm', 11, 500, FG4, ls=1) + T(cx, Y + 90, val, 's', 19, 600, PINK if lab == 'DROPPED' else FG))
        cx0, cy0, ch = X + 20, Y + 224, 96
        thr = cy0 - ch * .55
        heights = [.32, .28, .36, .3, .42, .34, .3, .27, .38, .33, .88, .31, .29, .35, .4, .3, .26, .33, .37, .31,
                   .29, .72, .34, .3, .28, .36, .32, .3, .27, .34, .39, .3]
        bw = (PW - 40) / len(heights)
        for i, hgt in enumerate(heights):
            bh = ch * hgt
            o.append(f'<rect x="{n(cx0 + i * bw + 1.5)}" y="{n(cy0 - bh)}" width="{n(bw - 3)}" height="{n(bh)}" rx="1.5" '
                     f'fill="{PINK if hgt > .55 else "url(#gradBar)"}" class="bar" '
                     f'style="animation-duration:{1.6 + (i * 7 % 11) * .12:.2f}s;animation-delay:-{(i * 5 % 9) * .2:.1f}s"/>')
        o.append(f'<line x1="{cx0}" y1="{n(thr)}" x2="{X + PW - 20}" y2="{n(thr)}" stroke="rgba(245,184,255,.45)" stroke-dasharray="3 4"/>'
                 + T(X + PW - 20, thr - 7, '16 ms', 'm', 11, 500, PINK, 'end'))
        o.append(T(X + 20, Y + PH - 14, 'kDebugMode only  ·  no-op in release', 'm', 11, 500, FG4, ls=.6))
    b.append(''.join(o))
    css = ('.bar{transform-box:fill-box;transform-origin:50% 100%;animation:bar 2s ease-in-out infinite alternate}'
           '@keyframes bar{0%{transform:scaleY(.65)}100%{transform:scaleY(1.08)}}')
    defs = ('<linearGradient id="gradBar" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#8ec5ff" stop-opacity=".5"/>'
            '<stop offset="1" stop-color="#b4a2ff"/></linearGradient>')
    title = ('Selected work, 04: performance_guard, an open-source Flutter package. A debug-only widget that overlays rebuild '
             'counts, frame drops and memory usage in-app, with zero cost in release mode.')
    save('work-perf.svg', doc(W, H, ''.join(b), css, defs, title, glow(960, 150, 380, 'P', .14)))


# ════════════════════════════════════════════════════════════════════════════
# STACK
# ════════════════════════════════════════════════════════════════════════════

def stack():
    W = 1200
    total = sum(len(items) for _, items in STACK)
    b = [section_head(W, '03', 'TOOLKIT', 'The stack behind ', 'the apps.', f'{total} TOOLS  ·  6 DISCIPLINES')]
    gap = 16
    colw = (W - 2 * M - 2 * gap) / 3
    accents = [BLUE, VIOLET, MINT, PINK, AMBER, FG3]
    y0 = 156
    for row in range(2):
        built = []
        for col in range(3):
            k = row * 3 + col
            title_, items = STACK[k]
            x = M + col * (colw + gap)
            cf, bottom = chip_flow(x + 20, y0 + 70, colw - 40, tagged(items, accents[k]), gap=7, rowgap=8)
            built.append((x, title_, items, cf, bottom, k))
        ph = max(bt[4] for bt in built) - y0 + 22
        for x, title_, items, cf, _, k in built:
            b.append(f'<g><rect x="{n(x)}" y="{y0}" width="{n(colw)}" '
                     f'height="{n(ph)}" rx="18" fill="{SURFACE}" stroke="{LINE}"/>'
                     f'<rect x="{n(x + 20)}" y="{y0}" width="40" height="2" fill="{accents[k]}"/>'
                     + T(x + 20, y0 + 44, f'0{k + 1}', 'm', 14, 500, FG4, ls=1.2)
                     + T(x + 54, y0 + 44, title_, 's', 22, 600, FG, ls=-.4)
                     + T(x + colw - 20, y0 + 44, f'{len(items)}', 'm', 14, 500, FG4, 'end')
                     + cf + '</g>')
        y0 += ph + gap
    H = int(y0 - gap + 8)
    title = 'Toolkit. ' + ' '.join(f'{t}: {", ".join(i[0] for i in items)}.' for t, items in STACK)
    glows = glow(120, 40, 420, 'B', .14) + glow(1100, H - 40, 420, 'P', .12)
    save('stack.svg', doc(W, H, ''.join(b), '', '', title, glows))


# ════════════════════════════════════════════════════════════════════════════
# FOOTER + BUTTONS
# ════════════════════════════════════════════════════════════════════════════

def footer():
    W, H = 1200, 340
    glows = glow(600, 250, 460, 'V', .42, 'd1') + glow(320, 230, 340, 'B', .26, 'd2') + glow(880, 230, 340, 'P', .22, 'd3')
    css = ['.d1{animation:d1 16s ease-in-out infinite alternate}@keyframes d1{to{transform:translate(0,-24px)}}'
           '.d2{animation:d2 20s ease-in-out infinite alternate}@keyframes d2{to{transform:translate(60px,-20px)}}'
           '.d3{animation:d3 18s ease-in-out infinite alternate}@keyframes d3{to{transform:translate(-60px,-20px)}}']
    gd, gb = grid(W, H, 48, 600, 200, 420)
    b = [gb, pill(600, 30, 'AVAILABLE FOR OPPORTUNITIES', anchor='middle'),
         T(600, 146, 'Let’s build something', 's', 60, 600, FG, 'middle', ls=-2.2),
         T(600, 220, 'people love to use.', 'i', 74, 400, 'url(#grad)', 'middle'),
         T(600, 290, f'{EMAIL}  ·  Pune, India  ·  UTC+5:30', 'm', 17, 500, FG2, 'middle', ls=.3)]
    save('footer.svg', doc(W, H, ''.join(b), ''.join(css), gd,
                           f'Let’s build something people love to use. Email {EMAIL}. Pune, India.', glows))


def _ico_arrow(x, cy, c):
    return (f'<path d="M{x} {cy + 5}L{x + 10} {cy - 5}M{x + 2} {cy - 5}H{x + 10}V{cy + 3}" fill="none" stroke="{c}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'), 10


def _ico_linkedin(x, cy, c):
    return (f'<rect x="{x}" y="{cy - 8}" width="16" height="16" rx="3.5" fill="#0a66c2"/>'
            + T(x + 8, cy + 4.2, 'in', 's', 11, 700, '#fff', 'middle', ls=-.2)), 16


def _ico_doc(x, cy, c):
    return (f'<g fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M{x + 2} {cy - 8}H{x + 10}L{x + 14} {cy - 4}V{cy + 8}H{x + 2}Z"/>'
            f'<path d="M{x + 5} {cy}H{x + 11}M{x + 5} {cy + 3.5}H{x + 9}"/></g>'), 16


def _ico_mail(x, cy, c):
    return (f'<g fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"><rect x="{x}" y="{cy - 6.5}" width="17" height="13" rx="2.5"/>'
            f'<path d="M{x + 1} {cy - 5}L{x + 8.5} {cy + 1}L{x + 16} {cy - 5}" stroke-linecap="round"/></g>'), 17


def _ico_leetcode(x, cy, c):
    return icon('leetcode', x, cy - 8, 16), 16


def button(name, text, ico, primary=False):
    h, size, pad = 48, 15, 20
    weight = 600 if primary else 500
    iw = ico(0, 0, FG)[1]
    w = pad + iw + 10 + tw(text, 's', size, weight) + pad
    fg = '#0b0b0e' if primary else FG
    if primary:
        bg = (f'<rect width="{n(w)}" height="{h}" rx="{h / 2}" fill="url(#gradP)"/><clipPath id="bc"><rect width="{n(w)}" '
              f'height="{h}" rx="{h / 2}"/></clipPath><g clip-path="url(#bc)"><g class="shine"><rect x="-60" y="-10" '
              f'width="30" height="70" fill="rgba(255,255,255,.5)" transform="skewX(-22)"/></g></g>')
        content = T(pad, h / 2 + size * .35, text, 's', size, weight, fg) + ico(w - pad - iw, h / 2, fg)[0]
    else:
        bg = (f'<rect x=".5" y=".5" width="{n(w - 1)}" height="{h - 1}" rx="{(h - 1) / 2}" fill="{BTN}" '
              f'stroke="{BTN_STROKE}"/>')
        content = ico(pad, h / 2, fg)[0] + T(pad + iw + 10, h / 2 + size * .35, text, 's', size, weight, fg)
    css = (".s{font-family:G,ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}"
           f".shine{{animation:shine 4.5s cubic-bezier(.5,0,.3,1) infinite 1s}}"
           f"@keyframes shine{{0%{{transform:translateX(0)}}40%,100%{{transform:translateX({n(w + 120)}px)}}}}"
           "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
    save(name, f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(w)}" height="{h}" viewBox="0 0 {n(w)} {h}" role="img" '
               f'aria-label="{escape(text)}"><title>{escape(text)}</title><style>{font_css()}{css}</style>'
               f'<defs>{_gradient("gradP", PASTEL)}</defs>{bg}{content}</svg>')


def buttons():
    button('btn-portfolio.svg', 'Portfolio', _ico_arrow, primary=True)
    button('btn-linkedin.svg', 'LinkedIn', _ico_linkedin)
    button('btn-resume.svg', 'Résumé', _ico_doc)
    button('btn-email.svg', 'Email', _ico_mail)
    button('btn-leetcode.svg', 'LeetCode', _ico_leetcode)


if __name__ == '__main__':
    print('Building cards' + (' (per-card font subsets)…' if _ft_subset else '…'))
    for name in THEMES:
        apply_theme(name)
        hero()
        about()
        experience()
        work_akbar()
        work_halves()
        work_perf()
        stack()
        footer()
        buttons()
    print('Done.')
