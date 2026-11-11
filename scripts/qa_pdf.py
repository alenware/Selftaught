#!/usr/bin/env python3
"""Visual and text QA for a built study guide.

    qa_pdf.py outputs/My guide.pdf --source reports/My guide.md

1. Rasterizes the sample pages listed in <pdf>.qa.json (written by build_pdf.py:
   cover, table of contents, a chapter opening, the longest and widest code
   blocks, the widest table, the callouts, the sources appendix, the last page)
   to PNG files, so they can be opened and looked at.
2. Checks the text layer: empty pages, replacement characters, fonts that are
   not part of the design (a sign of missing glyphs) and, when --source is
   given, that the words of the markdown made it into the PDF.

Uses Poppler (pdftoppm, pdftotext, pdffonts) when installed, PyMuPDF otherwise.
Exit status is 1 when a check fails. Looking at the PNGs is still required:
this script cannot see an ugly page.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

EXPECTED_FONTS = ("pagella", "inter", "dejavu")


def have(tool):
    return shutil.which(tool) is not None


def page_texts(pdf):
    if have("pdftotext"):
        out = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
                             capture_output=True, check=True).stdout.decode("utf-8", "replace")
        pages = out.split("\f")
        return pages[:-1] if pages and not pages[-1].strip() else pages
    import fitz  # PyMuPDF
    with fitz.open(pdf) as doc:
        return [p.get_text() for p in doc]


def font_names(pdf):
    if have("pdffonts"):
        out = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout
        return sorted({l.split()[0].split("+")[-1] for l in out.splitlines()[2:] if l.strip()})
    import fitz
    names = set()
    with fitz.open(pdf) as doc:
        for p in doc:
            names |= {f[3].split("+")[-1] for f in p.get_fonts()}
    return sorted(names)


def rasterize(pdf, pages, out_dir, dpi):
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for p in pages:
        target = out_dir / f"page-{p:03d}.png"
        if have("pdftoppm"):
            subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(p), "-l", str(p),
                            "-singlefile", str(pdf), str(target.with_suffix(""))], check=True)
        else:
            import fitz
            with fitz.open(pdf) as doc:
                doc[p - 1].get_pixmap(dpi=dpi).save(target)
        made.append(target)
    return made


def squash(text):
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    return re.sub(r"[\s\-‐‑]+", "", text).lower()


def source_words(md):
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)            # front-matter
    md = re.sub(r"^##\s+(Tabla de contenidos?|Table of contents)\s*\n.*?(?=^---|^## )", "",
                md, flags=re.S | re.M | re.I)                        # hand-written TOC
    md = re.sub(r"\]\((https?://[^)\s]+)\)", "] ", md)               # link targets
    md = re.sub(r"^```[^\n]*$", " ", md, flags=re.M)                 # fence lines
    md = re.sub(r"^\s*\|?[\s:|-]+\|?\s*$", " ", md, flags=re.M)      # table rules
    return {w.lower() for w in re.findall(r"[^\W\d_]{5,}", unicodedata.normalize("NFKC", md))}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--source", type=Path, help="markdown the PDF was built from")
    ap.add_argument("--out", type=Path, help="folder for the PNGs (default: <pdf folder>/qa)")
    ap.add_argument("--pages", type=int, nargs="+", help="extra pages to rasterize")
    ap.add_argument("--dpi", type=int, default=80)
    args = ap.parse_args()

    pdf = args.pdf.resolve()
    plan_file = pdf.with_suffix(".qa.json")
    plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
    texts = page_texts(pdf)
    problems = []

    print(f"{pdf.name}: {len(texts)} pages")
    for w in plan.get("warnings", []):
        problems.append(f"build warning: {w}")

    empty = [i for i, t in enumerate(texts, 1) if len(t.strip()) < 3]
    if empty:
        problems.append(f"pages without text (blank?): {empty}")
    bad = [i for i, t in enumerate(texts, 1) if "�" in t]
    if bad:
        problems.append(f"replacement characters (broken glyphs) on pages: {bad}")
    sparse = [i for i, t in enumerate(texts[2:-1], 3) if 3 <= len(t.strip()) < 250]
    if sparse:
        print(f"nearly empty pages worth a look: {sparse}")

    fonts = font_names(pdf)
    print("fonts: " + ", ".join(fonts))
    odd = [f for f in fonts if not any(k in f.lower() for k in EXPECTED_FONTS)]
    if odd:
        problems.append(f"fonts outside the design (missing glyphs fell back?): {odd}")

    if args.source:
        words = source_words(args.source.read_text(encoding="utf-8"))
        hay = squash("\n".join(texts))
        missing = sorted(w for w in words if squash(w) not in hay)
        kept = 100 * (1 - len(missing) / max(len(words), 1))
        print(f"text retention: {kept:.1f}% of {len(words)} distinct source words found")
        if missing:
            print("  not found: " + ", ".join(missing[:40]))
        if kept < 99:
            problems.append(f"only {kept:.1f}% of the source words are in the PDF")

    pages = [s["page"] for s in plan.get("samples", [])] or [1, 2, 3, len(texts)]
    pages = sorted({p for p in pages + (args.pages or []) + sparse[:4] if 1 <= p <= len(texts)})
    why = {s["page"]: s["why"] for s in plan.get("samples", [])}
    out_dir = (args.out or pdf.parent / "qa").resolve()
    print("look at these pages:")
    for p, png in zip(pages, rasterize(pdf, pages, out_dir, args.dpi)):
        print(f"  {png}  ({why.get(p, 'extra')})")

    for p in problems:
        print(f"PROBLEM  {p}")
    print("text checks: " + ("FAILED" if problems else "ok"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
