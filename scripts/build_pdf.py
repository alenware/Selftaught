#!/usr/bin/env python3
"""Build a study-guide PDF: markdown -> HTML -> WeasyPrint (A4).

    build_pdf.py reports/My guide.md -o outputs/My guide.pdf

The markdown source is never modified; every transformation happens here.
Cover data comes from the YAML front-matter of the markdown file and can be
overridden with command-line flags. Nothing about a specific guide lives in
this script or in the stylesheet.

Front-matter keys (all optional):
    title, kicker, subtitle, date, short_title, chips (list), lang (es|en),
    stats (list of [value, label] pairs; replaces the automatic metrics)

Besides the PDF it writes <output>.qa.json with the page count, the pages worth
looking at during visual QA and any layout warnings.
"""
import argparse
import datetime as dt
import html
import json
import math
import re
import sys
import tempfile
from pathlib import Path

import markdown
import yaml
from bs4 import BeautifulSoup, NavigableString, Tag
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound
from weasyprint import HTML

SKILL = Path(__file__).resolve().parent.parent
STYLE = SKILL / "assets" / "style.css"
FONTS = SKILL / "assets" / "fonts"

SHORT_CODE_LINES = 34   # blocks up to this many lines are kept on one page
MONO_ADVANCE = 0.602    # DejaVu Sans Mono glyph width, in em
CODE_WIDTH_PT = 474     # usable width inside a full-width code block (A4, 18 mm margins)
CODE_PT, DIAGRAM_PT = 7.8, 7.6          # default sizes, mirrored in style.css
CODE_MIN_PT, DIAGRAM_MIN_PT = 6.6, 5.2  # how far a wide block may be shrunk

# --------------------------------------------------------------------------
# 0. Language-dependent labels
# --------------------------------------------------------------------------
LABELS = {
    "es": {
        "chip": "GUÍA DE ESTUDIO", "kicker": "Guía de estudio:", "intro": "Introducción",
        "chapter": "Capítulo", "toc_kicker": "ÍNDICE", "toc_title": "Contenido",
        "appendix": "Apéndice", "sources": "Índice de fuentes citadas", "ch_abbr": "cap.",
        "stat_chapters": "capítulos", "stat_code": "bloques de código",
        "stat_sources": "fuentes citadas", "stat_levels": "checklists por nivel",
        "callout_checklist": "Checklist por nivel",
        "callout_interview": "Preparación de entrevista",
        "author": "Guía de estudio",
        "appendix_intro": (
            "Cada número volado del texto (p. ej. {sample}) remite a esta lista. Las URL "
            "idénticas se agrupan en una sola entrada; si una misma fuente aparece con títulos "
            "distintos en el texto, se muestran todos. Entre paréntesis, el capítulo donde se "
            "cita. Todas las direcciones son enlaces activos. Total: {n} fuentes únicas."),
        "months": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
                   "Septiembre", "Octubre", "Noviembre", "Diciembre"],
    },
    "en": {
        "chip": "STUDY GUIDE", "kicker": "Study guide:", "intro": "Introduction",
        "chapter": "Chapter", "toc_kicker": "INDEX", "toc_title": "Contents",
        "appendix": "Appendix", "sources": "Index of cited sources", "ch_abbr": "ch.",
        "stat_chapters": "chapters", "stat_code": "code blocks",
        "stat_sources": "cited sources", "stat_levels": "checklists by level",
        "callout_checklist": "Checklist by level",
        "callout_interview": "Interview preparation",
        "author": "Study guide",
        "appendix_intro": (
            "Every superscript number in the text (e.g. {sample}) points to this list. "
            "Identical URLs are grouped into one entry; when the same source appears under "
            "different titles, all of them are shown. In parentheses, the chapter that cites "
            "it. Every address is a live link. Total: {n} unique sources."),
        "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                   "September", "October", "November", "December"],
    },
}

# --------------------------------------------------------------------------
# 1. Front-matter and code fences
# --------------------------------------------------------------------------
FRONT_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n", re.S)
FENCE_RE = re.compile(r"^([ \t]*)```([^\n`]*)\n(.*?)^\1```[ \t]*$", re.S | re.M)
LANG_LABEL = {
    "python": "Python", "py": "Python", "pycon": "Python REPL", "bash": "Bash", "sh": "Shell",
    "shell": "Shell", "console": "Terminal", "powershell": "PowerShell", "ini": "INI",
    "toml": "TOML", "json": "JSON", "markdown": "Markdown", "sql": "SQL", "nginx": "nginx",
    "http": "HTTP", "graphql": "GraphQL", "protobuf": "Protocol Buffers", "yaml": "YAML",
    "yml": "YAML", "dockerfile": "Dockerfile", "docker": "Dockerfile",
    "hcl": "HCL / Terraform", "terraform": "HCL / Terraform", "promql": "PromQL",
    "javascript": "JavaScript", "js": "JavaScript", "typescript": "TypeScript",
    "ts": "TypeScript", "go": "Go", "rust": "Rust", "java": "Java", "c": "C", "cpp": "C++",
    "diff": "Diff", "gitignore": ".gitignore", "makefile": "Makefile", "html": "HTML",
    "css": "CSS", "xml": "XML", "text": "", "txt": "", "": "",
}
FORMATTER = HtmlFormatter(nowrap=True)
BOX_CHARS = "─│└┘├┤┬┴┼►◄┌┐▲▼═║╔╗╚╝"
PLACEHOLDER_RE = re.compile(r"(?:<p>\s*)?CODEBLOCKPLACEHOLDER(\d+)X(?:\s*</p>)?")


def split_front_matter(text):
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        sys.exit(f"front-matter is not valid YAML: {exc}")
    if not isinstance(meta, dict):
        return {}, text
    return meta, text[m.end():]


def dedent(code, indent):
    if not indent:
        return code
    return "\n".join(l[len(indent):] if l.startswith(indent) else l.lstrip()
                     for l in code.split("\n"))


def render_code(lang, code, index, warnings):
    lang = lang.strip().split()[0].lower() if lang.strip() else ""
    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    code = code.rstrip("\n").expandtabs(4)
    body = highlight(code, lexer, FORMATTER).rstrip("\n")
    lines = code.split("\n")
    nlines = len(lines)
    maxlen = max(len(l) for l in lines)
    classes = ["codeblock"]
    if nlines <= SHORT_CODE_LINES:
        classes.append("short")
    is_diagram = lang in ("", "text", "txt") and any(ch in code for ch in BOX_CHARS)
    if is_diagram:
        classes.append("diagram")

    # Wide blocks: shrink the type a little instead of wrapping or overflowing.
    base, floor = (DIAGRAM_PT, DIAGRAM_MIN_PT) if is_diagram else (CODE_PT, CODE_MIN_PT)
    style = ""
    if maxlen * MONO_ADVANCE * base > CODE_WIDTH_PT:
        fit = math.floor(CODE_WIDTH_PT / (MONO_ADVANCE * maxlen) * 10) / 10
        if fit >= floor:
            style = f' style="font-size:{fit}pt"'
        else:
            style = f' style="font-size:{floor}pt"'
            what = "will overflow the page" if is_diagram else "will wrap"
            warnings.append(f"code block {index + 1} ({lang or 'diagram'}): longest line is "
                            f"{maxlen} characters and {what}; shorten it in the markdown")
    label = LANG_LABEL.get(lang, lang.upper() if len(lang) <= 4 else lang.capitalize())
    label_html = f'<div class="code-lang">{html.escape(label)}</div>' if label else ""
    return (f'<div class="{" ".join(classes)}" id="code-{index + 1}" data-lines="{nlines}" '
            f'data-maxlen="{maxlen}">{label_html}<pre class="hl"{style}><code>{body}</code>'
            f'</pre></div>')


def extract_code(md_text, warnings):
    blocks = []

    def repl(m):
        indent = m.group(1)
        blocks.append(render_code(m.group(2), dedent(m.group(3), indent), len(blocks),
                                  warnings))
        return f"\n\n{indent}CODEBLOCKPLACEHOLDER{len(blocks) - 1}X\n\n"

    return FENCE_RE.sub(repl, md_text), blocks


# --------------------------------------------------------------------------
# 2. Links -> numbered superscript references
# --------------------------------------------------------------------------
class Sources:
    def __init__(self):
        self.by_url = {}   # url -> number
        self.items = []    # list of dicts: url, titles, chapters

    def ref(self, url, title, chapter):
        if url not in self.by_url:
            self.by_url[url] = len(self.items) + 1
            self.items.append({"url": url, "titles": [], "chapters": []})
        it = self.items[self.by_url[url] - 1]
        t = re.sub(r"\s+", " ", BeautifulSoup(title, "html.parser").get_text()).strip()
        if t and t != url and t not in it["titles"]:
            it["titles"].append(t)
        if chapter not in it["chapters"]:
            it["chapters"].append(chapter)
        return self.by_url[url]


# Reliability tags, Spanish and English spellings.
T_OK = r"verificad[ao]|verified"
T_REF = r"ref\. canónica|canonical ref\."
T_NV = r"no verificad[ao]|unverified"
T_SYN = r"síntesis|synthesis"
T_CG = r"CG|GK"

A_RE = r'<a href="(https?://[^"]+)">(.*?)</a>'
PAREN_GROUP_RE = re.compile(
    r"\s*\(\s*(" + A_RE + r"(?:\s*[;,]\s*" + A_RE + r")*)\s*\)")
SINGLE_A_RE = re.compile(A_RE)
TOKEN_RE = re.compile(r"(?P<paren>" + PAREN_GROUP_RE.pattern + r")|(?P<single>" + A_RE + r")")
TAG_MIXED_RE = re.compile(
    rf"\[(?P<tag>{T_OK}|{T_REF}|{T_NV}|{T_CG})[,;:]\s*(?P<inner>[^\[\]<]*<[^\[\]]*?)\]")
TAG_GROUP_RE = re.compile(
    rf"\[(?P<tag>{T_OK}|{T_REF}|{T_NV}|(?:{T_CG})(?:; lectura|; reading)?)[:;]\s*"
    r"(?P<inner>(?:(?!</?a[ >])[^\[\]])*<a href=[^\[\]]*?</a>[^\[\]]*?)\]")
TAG_RE = re.compile(
    rf"\[({T_OK}|{T_REF}|{T_NV}|{T_SYN}|(?:{T_CG})(?:[;,][^\]]*| salvo cita| unless cited)?)\]")


def badge_class(tag):
    if re.match(T_OK, tag):
        return "badge-ok"
    if re.match(T_REF, tag):
        return "badge-ref"
    if re.match(T_NV, tag):
        return "badge-nv"
    if re.match(T_SYN, tag):
        return "badge-syn"
    if tag in ("CG", "GK"):
        return "badge-cg"
    return "badge-cgx"  # CG/GK with a qualifier


def sup_html(nums_urls):
    parts = [f'<a class="cite-num" href="{html.escape(u, quote=True)}">{n}</a>'
             for n, u in nums_urls]
    return '<sup class="cite">' + '<span class="cite-sep">,</span>'.join(parts) + "</sup>"


def convert_links(fragment_html, sources, chapter):
    """Number the links of one chapter's HTML (document order is preserved)."""

    def repl(m):
        if m.group("paren"):
            nums = []
            for url, title in SINGLE_A_RE.findall(m.group("paren")):
                url_u = html.unescape(url)
                nums.append((sources.ref(url_u, title, chapter), url_u))
            return sup_html(nums)
        am = SINGLE_A_RE.match(m.group("single"))
        url_u = html.unescape(am.group(1))
        n = sources.ref(url_u, am.group(2), chapter)
        return (f'<a class="ext" href="{am.group(1)}">{am.group(2)}</a>'
                + sup_html([(n, url_u)]))

    def group_repl(m):
        tag = m.group("tag")
        return (f'<span class="refgroup"><span class="badge {badge_class(tag)}">{tag}</span> '
                f'{m.group("inner").strip()}</span>')

    pieces = re.split(r"(<pre[\s\S]*?</pre>)", fragment_html)  # never touch code blocks
    out = []
    for p in pieces:
        if not p.startswith("<pre"):
            # "[ref. canónica: <a>..</a>; <a>..</a>]" -> badge + linked titles
            p = TAG_GROUP_RE.sub(group_repl, p)
            p = TOKEN_RE.sub(repl, p)
            p = TAG_MIXED_RE.sub(group_repl, p)
        out.append(p)
    return "".join(out)


def add_badges(soup):
    for text in list(soup.find_all(string=TAG_RE)):
        if text.find_parent(["pre", "code", "style", "title"]):
            continue
        s = str(text)
        new, last = [], 0
        for m in TAG_RE.finditer(s):
            if m.start() > last:
                new.append(NavigableString(s[last:m.start()]))
            sp = soup.new_tag("span", attrs={"class": f"badge {badge_class(m.group(1))}"})
            sp.string = m.group(1)
            new.append(sp)
            last = m.end()
        if last < len(s):
            new.append(NavigableString(s[last:]))
        for n in new:
            text.insert_before(n)
        text.extract()


# --------------------------------------------------------------------------
# 3. Structure: chapters, callouts, notes
# --------------------------------------------------------------------------
CHAPTER_RE = re.compile(r"^(\d+)[.:]\s+(.*)$")
CHECKLIST_RE = re.compile(r"^(\d+\.\d+\s+)?Checklist", re.I)
INTERVIEW_RE = re.compile(
    r"^(\d+\.\d+\s+)?(Preguntas de entrevista|Banco de preguntas|Interview questions|"
    r"Question bank)", re.I)
TOC_HEADING_RE = re.compile(r"^(Tabla de contenidos?|Índice|Contenidos?|Table of contents|"
                            r"Contents)$", re.I)
NOTE_RE = re.compile(r"^(Sobre |Convención|Nota|Advertencia|Importante|Cuidado|Atención|Ojo|"
                     r"Consejo|About |Convention|Note|Warning|Important|Caution|Tip)")


def build_body(md_html, labels, fallback_title):
    soup = BeautifulSoup(md_html, "html.parser")
    top = [n for n in soup.contents if not (isinstance(n, NavigableString) and not n.strip())]

    chapters = []  # dicts: num, label, title, nodes (html strings or callout dicts)
    cur = None
    callout = None
    skipping_toc = False
    sec_counter = 0

    def intro(title):
        ch = {"num": None, "label": labels["intro"], "title": title, "nodes": [],
              "id": "intro", "subs": [], "title_html": None}
        chapters.append(ch)
        return ch

    def close_callout():
        nonlocal callout
        if callout is not None:
            cur["nodes"].append(callout)
            callout = None

    def emit(node_html):
        if callout is not None:
            callout["children"].append(node_html)
        else:
            cur["nodes"].append(node_html)

    for node in top:
        if isinstance(node, NavigableString):
            if cur is not None:
                emit(str(node))
            continue
        name = node.name
        text = node.get_text().strip()

        if name == "h1":
            close_callout() if cur is not None else None
            cur = intro(text)
            continue
        if name == "h2":
            if cur is not None:
                close_callout()
            if TOC_HEADING_RE.match(text):
                skipping_toc = True   # the PDF builds its own table of contents
                continue
            skipping_toc = False
            m = CHAPTER_RE.match(text)
            if m:
                cur = {"num": m.group(1), "label": f"{labels['chapter']} {m.group(1)}",
                       "title": m.group(2), "nodes": [], "id": f"cap-{m.group(1)}",
                       "subs": [],
                       # keep the inline markup of the title (minus the number)
                       "title_html": re.sub(r"^\s*\d+[.:]\s+", "", node.decode_contents())}
                chapters.append(cur)
                continue
            if cur is None:
                cur = intro(fallback_title)
            # unnumbered h2 (e.g. "Cómo leer esta guía") -> section of the current chapter
            sec_counter += 1
            sid = f"sec-{sec_counter}"
            cur["subs"].append((sid, text))
            emit(f'<h2 id="{sid}">{node.decode_contents()}</h2>')
            continue
        if skipping_toc:
            if name == "hr":
                skipping_toc = False
            continue
        if cur is None:
            cur = intro(fallback_title)
        if name == "h3":
            close_callout()
            sec_counter += 1
            sid = f"sec-{sec_counter}"
            h = f'<h2 id="{sid}">{node.decode_contents()}</h2>'
            if CHECKLIST_RE.match(text):
                callout = {"kind": "checklist", "children": [h]}
            elif INTERVIEW_RE.match(text):
                callout = {"kind": "interview", "children": [h]}
            else:
                cur["subs"].append((sid, text))
                cur["nodes"].append(h)
            continue
        if name == "h4":
            emit(f"<h3>{node.decode_contents()}</h3>")
            continue
        if name in ("h5", "h6"):
            emit(f"<h4>{node.decode_contents()}</h4>")
            continue
        if name == "hr":
            close_callout()
            continue  # section separators: chapters already start on a new page
        if name == "p":
            first = node.contents[0] if node.contents else None
            if (isinstance(first, Tag) and first.name == "strong"
                    and NOTE_RE.match(first.get_text())):
                node["class"] = node.get("class", []) + ["note"]
        emit(str(node))
    if cur is not None:
        close_callout()
    return chapters


def render_callout(c, labels):
    plain = re.sub(r"<[^>]+>", "", "".join(c["children"]))
    compact = " compact" if len(plain) < 3800 else ""
    tag = labels[f"callout_{c['kind']}"]
    return (f'<div class="callout callout-{c["kind"]}{compact}">'
            f'<div class="callout-tag">{tag}</div>' + "".join(c["children"]) + "</div>")


# --------------------------------------------------------------------------
# 4. Cover
# --------------------------------------------------------------------------
COVER_SVG = """
<svg class="cover-art" viewBox="0 0 600 420" xmlns="http://www.w3.org/2000/svg">
  <g stroke="#7f8fe0" stroke-opacity="0.45" stroke-width="1.4" fill="none">
    <path d="M60 80 L200 40 L340 110 L480 60 L560 150"/>
    <path d="M60 80 L130 200 L270 230 L340 110"/>
    <path d="M130 200 L90 330 L230 370 L270 230 L420 260 L480 60"/>
    <path d="M420 260 L560 150 L540 330 L420 260"/>
    <path d="M230 370 L380 390 L420 260"/>
    <path d="M200 40 L270 230"/>
    <path d="M380 390 L540 330"/>
  </g>
  <g stroke="#9fb0ff" stroke-opacity="0.25" stroke-width="1" stroke-dasharray="4 6" fill="none">
    <circle cx="340" cy="110" r="58"/>
    <circle cx="270" cy="230" r="90"/>
  </g>
  <g fill="#c7d0ff">
    <circle cx="60" cy="80" r="5"/><circle cx="200" cy="40" r="4"/>
    <circle cx="480" cy="60" r="5"/><circle cx="560" cy="150" r="4"/>
    <circle cx="130" cy="200" r="4"/><circle cx="90" cy="330" r="5"/>
    <circle cx="230" cy="370" r="4"/><circle cx="380" cy="390" r="4"/>
    <circle cx="540" cy="330" r="5"/>
  </g>
  <g fill="#f5b544">
    <circle cx="340" cy="110" r="9"/><circle cx="270" cy="230" r="11"/>
    <circle cx="420" cy="260" r="8"/>
  </g>
  <g fill="none" stroke="#f5b544" stroke-opacity="0.6" stroke-width="1.5">
    <circle cx="270" cy="230" r="18"/>
  </g>
</svg>
"""


def build_cover(meta, labels, stats):
    title, subtitle = meta["title"], meta.get("subtitle") or ""
    # Long titles/subtitles get smaller type and a shorter illustration so the
    # stats row and the date never collide with the bottom band.
    weight = math.ceil(len(title) / 24) * 2 + math.ceil(len(subtitle) / 70)
    size = "cover-tight" if weight >= 9 else "cover-mid" if weight >= 7 else ""
    chips = meta.get("chips") or [labels["chip"]]
    if isinstance(chips, str):
        chips = [chips]
    chip_html = "".join(
        f'<span class="cover-chip{" ghost" if i else ""}">{html.escape(str(c))}</span>'
        for i, c in enumerate(chips[:3]))
    stat_html = "".join(f"<div><b>{html.escape(str(v))}</b><span>{html.escape(str(k))}</span>"
                        "</div>" for v, k in stats)
    sub_html = f'<p class="cover-subtitle">{html.escape(subtitle)}</p>' if subtitle else ""
    kicker = meta.get("kicker", labels["kicker"])
    kicker_html = f'<div class="cover-kicker">{html.escape(kicker)}</div>' if kicker else ""
    return f"""
<section class="cover {size}" data-short-title="{html.escape(meta['short_title'], quote=True)}">
  <div class="cover-band"></div>
  <div class="cover-inner">
    <div class="cover-top">{chip_html}</div>
    {COVER_SVG}
    {kicker_html}
    <h1 class="cover-title">{html.escape(title)}</h1>
    <div class="cover-accent"></div>
    {sub_html}
    <div class="cover-stats">{stat_html}</div>
    <div class="cover-date">{html.escape(str(meta['date']))}</div>
  </div>
  <div class="cover-bottom-band"><span></span><span></span><span></span></div>
</section>"""


# --------------------------------------------------------------------------
# 5. Assemble the document
# --------------------------------------------------------------------------
def glyph_warnings(soup):
    """Characters none of the bundled fonts can draw end up as empty boxes."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return []
    covered, mono = set(), set()
    for f in list(FONTS.glob("*.ttf")) + list(FONTS.glob("*.otf")):
        cmap = set(TTFont(f, lazy=True).getBestCmap())
        covered |= cmap
        if f.name.startswith("DejaVuSansMono"):
            mono |= cmap
    if not covered:
        return [f"no fonts found in {FONTS}; run scripts/fetch_fonts.py"]
    out = []
    code_text = "".join(p.get_text() for p in soup.find_all("pre"))
    all_text = soup.get_text()
    ok = {0x0A, 0x0D, 0x09, 0xAD, 0x200B}
    bad = sorted({c for c in all_text if ord(c) not in covered and ord(c) not in ok})
    bad_code = sorted({c for c in code_text if ord(c) not in mono and ord(c) not in ok})
    if bad:
        out.append("characters missing from every bundled font (they will render as empty "
                   "boxes or in a fallback font): "
                   + " ".join(f"{c} (U+{ord(c):04X})" for c in bad[:30]))
    if bad_code:
        out.append("characters in code blocks missing from DejaVu Sans Mono (alignment may "
                   "break): " + " ".join(f"{c} (U+{ord(c):04X})" for c in bad_code[:30]))
    return out


def build_html(src, overrides):
    warnings = []
    meta, md_text = split_front_matter(src.read_text(encoding="utf-8"))
    meta.update({k: v for k, v in overrides.items() if v is not None})
    lang = str(meta.get("lang", "es")).lower()[:2]
    labels = LABELS.get(lang, LABELS["en"])

    md_text, code_blocks = extract_code(md_text, warnings)
    md_html = markdown.markdown(md_text, extensions=["tables", "sane_lists"])
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", md_html, re.S)
    h1_text = re.sub(r"<[^>]+>", "", h1.group(1)).strip() if h1 else ""
    meta.setdefault("title", h1_text or src.stem)
    today = dt.date.today()
    meta.setdefault("date", f"{labels['months'][today.month - 1]} {today.year}")
    meta.setdefault("short_title", f"{labels['author']} · {meta['title']}")
    if len(meta["short_title"]) > 58:
        meta["short_title"] = meta["short_title"][:56].rsplit(" ", 1)[0].rstrip(",:;·") + "…"

    chapters = build_body(md_html, labels, meta["title"])
    chapters = [c for c in chapters if c["num"] is not None or c["nodes"]]
    sources = Sources()
    has_checklists = False

    chapter_html = []
    prev_plain = False  # previous chapter was a numbered one without callouts
    for ch in chapters:
        # Closing chapters (plan, resources, glossary, answers) carry no callouts.
        # From the second one in a row they continue on the same page.
        plain = ch["num"] is not None and not any(isinstance(n, dict) for n in ch["nodes"])
        flow = " flow" if plain and prev_plain else ""
        prev_plain = plain
        body = []
        for node in ch["nodes"]:
            if isinstance(node, dict):
                has_checklists = has_checklists or node["kind"] == "checklist"
                body.append(render_callout(node, labels))
            else:
                body.append(node)
        body_html = "\n".join(body)
        ch_ref = labels["intro"] if ch["num"] is None else f"{labels['ch_abbr']} {ch['num']}"
        body_html = convert_links(body_html, sources, ch_ref)
        body_html = PLACEHOLDER_RE.sub(lambda m: code_blocks[int(m.group(1))], body_html)
        title_html = ch.get("title_html") or html.escape(ch["title"])
        rt = ch["title"]
        if len(rt) > 62:
            rt = rt[:60].rsplit(" ", 1)[0].rstrip(",:;") + "…"
        running = (f"{labels['chapter']} {ch['num']} · {rt}" if ch["num"] is not None
                   else labels["intro"])
        big_num = (f'<div class="chapter-bignum">{ch["num"]}</div>'
                   if ch["num"] is not None else "")
        chapter_html.append(f"""
<section class="chapter{flow}" id="{ch['id']}">
  <div class="chapter-head">
    {big_num}
    <div class="chapter-label">{html.escape(ch['label'].upper())}</div>
    <h1 class="chapter-title" data-running="{html.escape(running, quote=True)}">{title_html}</h1>
    <div class="chapter-rule"><span></span></div>
  </div>
  {body_html}
</section>""")

    # Sources appendix
    appendix = ""
    if sources.items:
        src_items = []
        for i, it in enumerate(sources.items, 1):
            titles = " · ".join(html.escape(t) for t in it["titles"]) or html.escape(it["url"])
            src_items.append(
                f'<li id="src-{i}"><span class="src-num">{i}</span>'
                f'<span class="src-title">{titles}</span> '
                f'<span class="src-where">({html.escape(", ".join(it["chapters"]))})</span><br/>'
                f'<a class="src-url" href="{html.escape(it["url"], quote=True)}">'
                f'{html.escape(it["url"])}</a></li>')
        sample = '<sup class="cite"><a class="cite-num" href="#fuentes">12</a></sup>'
        running = f"{labels['appendix']} · {labels['sources']}"
        appendix = f"""
<section class="chapter appendix" id="fuentes">
  <div class="chapter-head">
    <div class="chapter-label">{labels['appendix'].upper()}</div>
    <h1 class="chapter-title" data-running="{html.escape(running, quote=True)}">{labels['sources']}</h1>
    <div class="chapter-rule"><span></span></div>
  </div>
  <p class="appendix-intro">{labels['appendix_intro'].format(sample=sample, n=len(sources.items))}</p>
  <ol class="sources">{''.join(src_items)}</ol>
</section>"""

    # Table of contents (tighter spacing when it would not fit one page)
    n_toc = sum(1 + len(c["subs"]) for c in chapters) + (1 if appendix else 0)
    dense = " dense" if 40 < n_toc <= 62 else ""
    toc = [f'<section class="toc-page" id="toc"><div class="toc-kicker">{labels["toc_kicker"]}'
           f'</div><h1 class="toc-title" data-running="{labels["toc_title"]}">'
           f'{labels["toc_title"]}</h1><div class="chapter-rule"><span></span></div>'
           f'<ul class="toc{dense}">']
    for ch in chapters:
        num = ch["num"] if ch["num"] is not None else "—"
        title_txt = (ch["title"] if ch["num"] is not None
                     else f"{labels['intro']}: {ch['title']}")
        toc.append(f'<li class="toc-ch"><a href="#{ch["id"]}"><span class="toc-num">{num}'
                   f'</span>{html.escape(title_txt)}</a></li>')
        for sid, st in ch["subs"]:
            toc.append(f'<li class="toc-sub"><a href="#{sid}">{html.escape(st)}</a></li>')
    if appendix:
        toc.append('<li class="toc-ch"><a href="#fuentes"><span class="toc-num">A</span>'
                   f'{labels["appendix"]}: {labels["sources"]}</a></li>')
    toc.append("</ul></section>")

    n_chapters = sum(1 for c in chapters if c["num"] is not None)
    counts = {"chapters": n_chapters, "code_blocks": len(code_blocks),
              "sources": len(sources.items)}
    stats = meta.get("stats")
    if not stats:
        stats = [(n_chapters, labels["stat_chapters"]),
                 (len(code_blocks), labels["stat_code"]),
                 (len(sources.items), labels["stat_sources"])]
        if has_checklists:
            stats.append(("J · M · S", labels["stat_levels"]))
    cover = build_cover(meta, labels, [tuple(s) for s in stats][:4])

    pyg_css = HtmlFormatter(style="friendly").get_style_defs(".hl")
    doc_title = f"{meta.get('kicker', labels['kicker'])} {meta['title']}".strip()
    doc = f"""<!DOCTYPE html>
<html lang="{html.escape(lang)}"><head><meta charset="utf-8">
<title>{html.escape(doc_title)}</title>
<meta name="author" content="{html.escape(str(meta.get('author', labels['author'])))}">
<meta name="description" content="{html.escape(str(meta.get('subtitle') or ''))}">
<meta name="dcterms.created" content="{today.isoformat()}">
<link rel="stylesheet" href="{STYLE.as_uri()}">
<style>{pyg_css}</style>
</head><body>
{cover}
{''.join(toc)}
{''.join(chapter_html)}
{appendix}
</body></html>"""
    soup = BeautifulSoup(doc, "html.parser")
    add_badges(soup)
    for i, t in enumerate(soup.find_all("table"), 1):
        ths = [th.get_text().strip() for th in t.find_all("th")]
        t["id"] = f"tbl-{i}"
        t["data-cols"] = str(len(ths))
        t["class"] = t.get("class", []) + [f"cols-{len(ths)}"]
        if ths and ths[0] in ("Nivel", "Level"):
            t["class"].append("level-table")
    # keep an intro paragraph ending with ':' together with a short code block after it
    for cb in soup.select("div.codeblock.short"):
        prev = cb.find_previous_sibling()
        if prev is not None and prev.name == "p" and prev.get_text().rstrip().endswith(":"):
            prev["class"] = prev.get("class", []) + ["keep-next"]
    left = soup.find_all(string=re.compile("CODEBLOCKPLACEHOLDER"))
    if left:
        warnings.append(f"{len(left)} code block placeholder(s) were not replaced")
    warnings += glyph_warnings(soup)
    return str(soup), soup, counts, warnings


def qa_plan(document, soup):
    """Pick the pages a human or the agent should look at after the build."""
    where = {}
    for i, page in enumerate(document.pages, 1):
        for name in page.anchors:
            where.setdefault(name, i)
    samples, seen = [], set()

    def add(page, why):
        if page and page not in seen:
            seen.add(page)
            samples.append({"page": page, "why": why})

    add(1, "cover")
    add(where.get("toc"), "table of contents")
    add(where.get("intro"), "introduction")
    add(where.get("cap-1"), "chapter opening")
    blocks = soup.select("div.codeblock")
    if blocks:
        longest = max(blocks, key=lambda b: int(b["data-lines"]))
        widest = max(blocks, key=lambda b: int(b["data-maxlen"]))
        add(where.get(longest["id"]), f"longest code block ({longest['data-lines']} lines)")
        add(where.get(widest["id"]), f"widest code block ({widest['data-maxlen']} chars)")
        diagram = soup.select_one("div.codeblock.diagram")
        if diagram:
            add(where.get(diagram["id"]), "text diagram")
    tables = soup.find_all("table")
    if tables:
        wide = max(tables, key=lambda t: (int(t["data-cols"]), len(t.get_text())))
        add(where.get(wide["id"]), f"widest table ({wide['data-cols']} columns)")
        big = max(tables, key=lambda t: len(t.get_text()))
        add(where.get(big["id"]), "largest table")
    for sel, why in ((".callout-checklist", "checklist callout"),
                     (".callout-interview", "interview callout"), ("p.note", "note box")):
        el = soup.select_one(sel)
        anchor = el.find(id=True) if el else None
        if anchor is None and el is not None:
            anchor = el.find_previous(id=True)
        if anchor is not None:
            add(where.get(anchor["id"]), why)
    add(where.get("fuentes"), "sources appendix")
    add(len(document.pages), "last page")
    return sorted(samples, key=lambda s: s["page"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source", type=Path, help="markdown study guide")
    ap.add_argument("-o", "--output", type=Path, help="PDF path (default: outputs/<name>.pdf)")
    ap.add_argument("--title")
    ap.add_argument("--kicker", help='small line above the title ("" hides it)')
    ap.add_argument("--subtitle")
    ap.add_argument("--date")
    ap.add_argument("--short-title", dest="short_title", help="running header text")
    ap.add_argument("--chips", nargs="+", help="up to three cover chips")
    ap.add_argument("--lang", help="es or en (labels and hyphenation)")
    ap.add_argument("--keep-html", type=Path, help="also save the intermediate HTML here")
    args = ap.parse_args()

    src = args.source.resolve()
    if not src.exists():
        sys.exit(f"not found: {src}")
    out = (args.output or Path("outputs") / (src.stem + ".pdf")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    overrides = {k: getattr(args, k) for k in
                 ("title", "kicker", "subtitle", "date", "short_title", "chips", "lang")}

    doc_html, soup, counts, warnings = build_html(src, overrides)
    if args.keep_html:
        args.keep_html.write_text(doc_html, encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "guide.html"
        html_path.write_text(doc_html, encoding="utf-8")
        document = HTML(filename=str(html_path)).render()
        document.write_pdf(str(out))

    report = {"pdf": str(out), "pages": len(document.pages), **counts,
              "samples": qa_plan(document, soup), "warnings": warnings}
    out.with_suffix(".qa.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"pages: {report['pages']}  chapters: {counts['chapters']}  "
          f"code blocks: {counts['code_blocks']}  sources: {counts['sources']}")
    for w in warnings:
        print(f"WARNING: {w}")
    print("QA pages: " + ", ".join(f"{s['page']} ({s['why']})" for s in report["samples"]))
    print(f"written: {out}")


if __name__ == "__main__":
    sys.exit(main())
