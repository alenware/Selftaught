---
name: selftaught
description: Research a topic with parallel subagents and turn it into a long, well-designed study-guide PDF with cited sources, reliability tags, commented code examples, checklists by level (junior/mid/senior), interview questions and a weekly study plan. Use when the user asks for a study guide or a complete guide on a topic, asks to break a topic down from scratch, or types /selftaught. Spanish triggers - "guía de estudio", "hazme una guía de estudio sobre X", "guía completa", "desglósame X desde cero". Not for a quick explanation in chat or a one-page summary.
---

# Selftaught: researched study guides as PDF

Turn "make me a study guide about X" into a PDF the reader can study from for weeks:
researched from primary sources, ordered from basics to advanced, with code that shows how
things work inside, and built to prepare for interviews.

The pipeline is fixed. The quality of the guide comes from following it in order:

```
intake → title and folders → decomposition → parallel research → writing
       → code check → PDF build → visual QA → delivery
```

`<skill>` below means the folder that contains this file. All output folders
(`research_notes/`, `reports/`, `outputs/`) are created in the current working directory.

## Reader profile (default)

Unless the user says otherwise, write for this reader:

- Self-taught developer, about one year of Python, programs with AI assistants, reads code
  well and is learning to debug it.
- Goal: senior developer / AI engineer.
- Wants clear explanations without childish simplification, and always wants to see what
  things look like inside, with code.

Write the guide in the language the user is writing in. Pass the profile and the language
to every subagent; they do not see this conversation.

## 1. Intake

Ask only when the answer would change the research: the topic is ambiguous, the level is
unclear, or the focus could go two different ways. One short question round at most. If
nothing is missing, start.

Settle the depth without asking when the request implies it:

| Depth | Pages | Subtopics | Searches per researcher | Chapters | Markdown length |
|---|---|---|---|---|---|
| short | 15–20 | 4 + 1 | about 8 | 4–5 | 4,000–5,000 words |
| standard (default) | 40–70 | 5–6 + 1 | about 15 | 7–10 | 10,500–18,000 words |
| deep | 80+ | 7 + 1 | 15–20 | 10–14 | 21,000+ words |

"Chapters" counts the content chapters; the four closing chapters (plan, resources,
glossary, answers) come on top. The length is the whole markdown file counted with `wc -w`,
code and tables included. A built guide runs at about 260 words per page, because every
content chapter starts a new page and code, boxes and the sources appendix take room. Give
the writer the word range, not the page range.

## 2. Title and folders

Choose a short title: 3–6 words, no punctuation, in the guide's language
(`Git desde cero hasta equipo`). It names everything:

```
research_notes/<title>/     one notes file per subtopic
reports/<title>.md          the guide
outputs/<title>.pdf         the deliverable
```

## 3. Decomposition

Split the topic into subtopics (count from the depth table) that do not overlap: if two
researchers would read the same documentation page, the split is wrong. Give each one 3–6
concrete questions to answer.

Always add one extra subtopic: **"current important concepts the user did not ask for"**.
Its researcher looks for what a senior practitioner would consider missing from the
request: recent changes, tools that replaced older ones, common misconceptions, and what
interviews ask today.

## 4. Parallel research

Launch one subagent per subtopic with the Agent (Task) tool, **all in the same turn** so
they run concurrently. Each prompt must contain, written out:

- the guide's topic, language, reader profile and depth;
- this researcher's subtopic, its questions, and the list of the other subtopics (so it
  stays out of them);
- the search budget from the depth table;
- the output path `research_notes/<title>/<subtopic-slug>.md`;
- an instruction to read `<skill>/references/researcher.md` first and follow it exactly
  (give the absolute path).

When they finish, open each notes file. Every question needs a Takeaway, cited findings
with URLs, and reliability tags. Relaunch a researcher whose file is missing, has findings
without URLs, or leaves most of its questions in Gaps.

## 5. Writing

Launch one writer subagent. Its prompt contains the topic, language, reader profile, depth
(target length from the table), the title, the notes folder, the output path
`reports/<title>.md`, and an instruction to read `<skill>/references/report-writer.md`
first and follow it exactly.

The result is a study guide, not an essay. The reference file defines the exact structure;
the parts that matter most:

- front-matter for the cover, a summary, the legend of reliability tags and a map of the
  learning route;
- numbered chapters in study order, from basic to advanced;
- short, correct code with comments in the guide's language, Python first, and real
  configuration files where they apply;
- at the end of every chapter, a checklist by level and an interview-question table;
- at the end of the guide, a weekly study plan with an integrating project, prioritized
  resources, a glossary and answers to the self-assessment questions;
- no figure without a source is stated as fact.

For deep guides the writer drafts the outline first and writes the file chapter by chapter,
appending as it goes, so no single response has to hold the whole guide.

After it finishes, read the guide yourself: check the structure against the reference, the
chapter order, and that security topics show code defensively (the vulnerable pattern at a
conceptual level next to the fix).

## 6. Code check

```bash
python <skill>/scripts/check_code.py "reports/<title>.md"
```

It parses every Python block with `ast.parse`, YAML with `yaml.safe_load`, JSON, TOML, and
bash with `bash -n`, and warns about lines too long for the page. Fix every error in the
markdown and run it again until it passes. Do not build the PDF with failing blocks. A
block that is deliberately incomplete is retagged `text`, or keeps its language with
`nocheck` after it.

## 7. PDF build

```bash
python <skill>/scripts/build_pdf.py "reports/<title>.md" -o "outputs/<title>.pdf"
```

The cover (title, kicker, subtitle, date, chips) comes from the front-matter of the
markdown and can be overridden with flags (`--title`, `--subtitle`, `--date`, `--kicker`,
`--short-title`, `--chips`, `--lang`). The metrics on the cover (chapters, code blocks,
cited sources) are counted from the document. Never edit the script or the stylesheet to
change a title.

The build prints warnings (lines that overflow, characters no bundled font can draw) and
writes `outputs/<title>.qa.json` with the pages to inspect. Fix warnings in the markdown
and rebuild. The design is described in `references/pdf-style.md`; read it before changing
`assets/style.css`.

## 8. Visual QA (mandatory)

```bash
python <skill>/scripts/qa_pdf.py "outputs/<title>.pdf" --source "reports/<title>.md"
```

It rasterizes the sample pages (cover, table of contents, a chapter opening, the longest
and widest code blocks, the widest table, the callouts, the sources appendix) into
`outputs/qa/` and checks the text layer for blank pages, broken glyphs, unexpected fonts
and words lost between the markdown and the PDF.

Then **open every PNG it lists with the Read tool and look at it**. The script cannot see
an ugly page. Look for:

- text or code running past the right margin or over another element;
- a table whose columns are crushed, or a header row that does not repeat;
- empty boxes where a character should be;
- a page that is blank or holds two orphan lines;
- a cover where the title, the stats row and the date collide.

If the page count printed by the build is more than about 15% outside the range for the
depth, send the writer back to cut or extend the markdown (whole low-priority sections
first, not an even thinning), then rebuild. Do not change the stylesheet to hit a count.

Fix the cause (usually in the markdown: shorten a code line, split a table, replace an
unsupported symbol), rebuild, and run the QA again. Finish only when the pages look right
and the text checks print `ok`.

## 9. Delivery

Leave the PDF in `outputs/` and show it to the user. Give a summary of 3–5 lines: what the
guide covers, its size (pages, chapters, code blocks, sources), where the reliability is
weakest (unverified items, gaps the researchers reported), and anything adjusted during QA.

## Environment

The scripts need Python 3.11+ with WeasyPrint (which needs Pango), `markdown`,
`beautifulsoup4`, `pygments` and `pyyaml`, plus Poppler or PyMuPDF for the QA.

- **Linux / WSL / macOS with apt-like setup:** run `bash <skill>/scripts/setup.sh` once. It
  installs the system libraries, creates the virtualenv `~/.venvs/selftaught`, downloads
  the fonts into `assets/fonts/` and prints `weasyprint --info`. Use
  `~/.venvs/selftaught/bin/python` for every script.
- **Windows:** run the scripts through WSL, where Pango installs cleanly. From PowerShell,
  in the folder that holds `reports/`:

  ```powershell
  wsl -- bash -lc '~/.venvs/selftaught/bin/python "$(wslpath -a "<skill>")/scripts/build_pdf.py" "reports/<title>.md" -o "outputs/<title>.pdf"'
  ```

  WSL starts in the current Windows folder, so the relative paths work. From Git Bash,
  prefix the command with `MSYS_NO_PATHCONV=1` so paths are not rewritten.
- **Fonts missing:** `python <skill>/scripts/fetch_fonts.py` downloads Inter, TeX Gyre
  Pagella and DejaVu into `assets/fonts/`. The stylesheet loads them with `@font-face`;
  nothing is read from system fonts.
- If WeasyPrint cannot be made to work, say so and stop before step 7. Do not deliver a PDF
  made with another tool as if it were the same design.

## Reference files

| File | Read it when |
|---|---|
| `references/researcher.md` | Every research subagent reads it first: search budget, primary sources, notes format, reliability tags. |
| `references/report-writer.md` | The writer subagent reads it first: exact structure of the guide, code rules, reliability rules. |
| `references/pdf-style.md` | Before touching `assets/style.css` or `build_pdf.py`, and when judging pages during visual QA. |
