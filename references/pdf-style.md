# PDF design

What the PDF looks like, which part of the markdown produces each element, and what to
check before changing `assets/style.css` or `scripts/build_pdf.py`. The design is fixed
across guides: only the content and the cover data change.

## Page

- A4, margins 22 mm top, 18 mm sides, 20 mm bottom.
- Running header: the guide's short title on the left, the current chapter on the right,
  both in small grey Inter, over a hairline. Footer: page number, centred.
- The cover and the first page of the table of contents have no header or footer.
- Every chapter starts on a new page. Its first page shows no running header. Exception:
  closing chapters (numbered chapters with no checklist or interview box) continue on the
  same page from the second one in a row, without the large number.

## Fonts

All fonts are bundled in `assets/fonts/` and loaded with `@font-face`. Nothing depends on
fonts installed on the machine.

| Use | Font | Notes |
|---|---|---|
| Body text | TeX Gyre Pagella 10.5 pt | Justified, hyphenated by `lang`. |
| Headings, tables, labels, cover | Inter (300–800) | |
| Code, diagrams | DejaVu Sans Mono 7.8 pt | Wide blocks shrink down to 6.6 pt. |
| Missing symbols | DejaVu Sans (as "Symbols") | Fallback for arrows and similar. |

A character none of these fonts has renders as an empty box. The build warns about each
one; replace it in the markdown.

## Colour

| Role | Colour |
|---|---|
| Navy (chapter titles; the cover gradient runs `#0b1233` to `#27378f`) | `#101a3f` |
| Indigo (section headings, table headers, links) | `#2f3f9e` |
| Amber accent (bands, labels, rules) | `#f5a524` |
| Checklist box | background `#eef8f1`, green `#1f8a4c` border and table header |
| Interview box | background `#fff7e8`, amber `#b26a00` headings, orange table header |
| Note box | background `#eef4fc`, blue `#1f63b8` left border |
| Body text | `#1d2233` |

## Elements and where they come from

| Element | Looks like | Markdown source |
|---|---|---|
| Cover | Full-page navy to indigo gradient, amber band at the top and three amber bars at the bottom, a network illustration, chips, kicker, title, amber accent line, subtitle, a row of metrics, date. | Front-matter (`title`, `kicker`, `subtitle`, `chips`, `date`) or CLI flags. Metrics are counted by the build. |
| Table of contents | "ÍNDICE / Contenido", chapters in bold with their number, sections indented, leader dots and page numbers. | Generated from `##` and `###` headings. |
| Chapter opening | Large pale chapter number, "CAPÍTULO N" label in amber, title in navy, short amber rule. | `## N. Title` |
| Section | Indigo Inter heading. | `### N.M Title` |
| Subsection | Smaller dark heading. | `####` |
| Code block | Light grey box with an indigo left border, language label as a tab at the top left, pygments "friendly" colours. | Fenced block with a language tag. |
| Diagram | Same box with an amber left border, no label, slightly smaller type, never wrapped. | Fenced block with no tag (or `text`) containing box-drawing characters. |
| Table | Indigo header row with white text that repeats on each page, zebra rows, small Inter. | Markdown table. |
| Reliability badge | Small rounded pill: green `verificada`, indigo `ref. canónica`, grey `CG`, red `no verificado`, violet `síntesis`. | The tag in square brackets. |
| Citation | A small superscript number linked to the source. A link written inline keeps its text and gets the number after it. | Markdown link. A link, or several, wrapped in one parenthesis becomes superscripts only. |
| Checklist box | Green box labelled "CHECKLIST POR NIVEL", level names highlighted in the first column. | `### Checklist …` until the next heading. |
| Interview box | Amber box labelled "PREPARACIÓN DE ENTREVISTA". | `### Preguntas de entrevista` until the next heading. |
| Note | Blue box with a left border. | Paragraph starting with bold `**Nota.**` and similar, or a blockquote. |
| Sources appendix | "APÉNDICE / Índice de fuentes citadas": two-column numbered list with title, chapters where cited and the URL as a live link. | Built from every link in the document. |

## Layout rules built into the script

- Code blocks of up to 34 lines are kept on one page; longer ones may break.
- A paragraph ending in `:` stays with the short code block that follows it.
- A code line too wide for the page shrinks the type of its block, down to a floor
  (6.6 pt for code, 5.2 pt for diagrams). Below the floor, code wraps and diagrams
  overflow, and the build prints a warning: shorten the line in the markdown.
- Long cover titles or subtitles switch the cover to a tighter variant with smaller type so
  the metrics row and the date do not reach the bottom bars.
- Small callouts are kept on one page; large ones may break between rows.
- Headings never sit alone at the bottom of a page.
- A table of contents with more than 40 entries uses tighter spacing so it fits one page
  (up to about 60 entries).

## Changing the design

- Change `assets/style.css` for appearance and `build_pdf.py` for structure. Keep guide
  data out of both: titles, dates and counts come from the markdown or the flags.
- `CODE_PT`, `DIAGRAM_PT` and `CODE_WIDTH_PT` in the script mirror values in the
  stylesheet. Change them together.
- Labels printed by the build ("Capítulo", "Contenido", "Apéndice"…) live in the `LABELS`
  dictionary, one entry per language. Add a language there.
- WeasyPrint supports paged-media CSS (`@page`, `string-set`, `target-counter`, `leader`)
  but not flexbox gaps in every version, grid in older versions, or JavaScript. Check the
  result of any change in the rendered pages, not in a browser.
- After any change, rebuild a guide and run the visual QA on the cover, the table of
  contents, a chapter opening, a page of code, a wide table and the appendix.

## What a correct page looks like

- Cover: nothing touches the bottom bars; the title is at most four lines.
- Table of contents: page numbers aligned to the right edge; no entry wraps under its
  number in a way that collides with the dots.
- Text pages: header present and showing the right chapter; no line of code or table cell
  past the right margin; no box split with one orphan line on the next page.
- Appendix: every entry has a number, a title and a URL; long URLs break instead of
  overflowing.
