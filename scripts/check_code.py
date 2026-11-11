#!/usr/bin/env python3
"""Validate the code blocks of a markdown study guide before building the PDF.

    check_code.py reports/My guide.md

Checks every fenced block by its language tag:
    python / py      ast.parse (syntax only; nothing is executed)
    yaml / yml       yaml.safe_load_all
    json             json.loads
    toml             tomllib.loads
    bash / sh        bash -n, when bash is available

Other languages are counted but not parsed. It also warns about lines too long
for the page, tabs, and tags the PDF cannot render (mermaid). A block that is
intentionally not valid on its own can opt out with "nocheck" after the
language:  ```python nocheck

Exit status is 1 when any block fails, so fix the markdown and run it again.
"""
import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import textwrap
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:  # the check degrades instead of crashing
    yaml = None
try:
    import tomllib
except ImportError:
    tomllib = None

FENCE_RE = re.compile(r"^([ \t]*)```([^\n`]*)\n(.*?)^\1```[ \t]*$", re.S | re.M)
BOX_CHARS = "─│└┘├┤┬┴┼►◄┌┐▲▼═║╔╗╚╝"
ALIASES = {"py": "python", "yml": "yaml", "sh": "bash", "shell": "bash"}


def check_python(code):
    ast.parse(code)


def check_yaml(code):
    if yaml is None:
        raise RuntimeError("PyYAML is not installed (pip install pyyaml)")
    list(yaml.safe_load_all(code))


def check_json(code):
    json.loads(code)


def check_toml(code):
    if tomllib is None:
        raise RuntimeError("tomllib needs Python 3.11+")
    tomllib.loads(code)


def check_bash(code):
    bash = shutil.which("bash")
    if not bash:
        return
    r = subprocess.run([bash, "-n"], input=code, text=True, capture_output=True,
                       encoding="utf-8")
    if r.returncode:
        raise SyntaxError(r.stderr.strip().splitlines()[0] if r.stderr.strip() else "bash -n")


CHECKS = {"python": check_python, "yaml": check_yaml, "json": check_json,
          "toml": check_toml, "bash": check_bash}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source", type=Path)
    ap.add_argument("--max-line", type=int, default=100,
                    help="warn about code lines longer than this (default 100)")
    args = ap.parse_args()
    text = args.source.read_text(encoding="utf-8")

    errors, warnings, counts, checked = [], [], Counter(), 0
    for n, m in enumerate(FENCE_RE.finditer(text), 1):
        line = text.count("\n", 0, m.start()) + 2      # first line of the code itself
        info = m.group(2).strip().lower().split()
        lang = ALIASES.get(info[0], info[0]) if info else ""
        code = textwrap.dedent(m.group(3))
        where = f"block {n} (line {line}, {lang or 'no language'})"
        counts[lang or "(none)"] += 1

        if lang == "mermaid":
            warnings.append(f"{where}: mermaid is not rendered in the PDF; draw the diagram "
                            "with box characters in an untagged block instead")
        if "\t" in code and lang != "makefile":
            warnings.append(f"{where}: contains tab characters; use spaces")
        if lang.startswith("python") and re.search(r"^\s*>>> ", code, re.M):
            warnings.append(f"{where}: looks like a REPL session; tag it ```pycon")
        longest = max((len(l) for l in code.split("\n")), default=0)
        diagram = not lang and any(c in code for c in BOX_CHARS)
        if longest > args.max_line and not diagram:
            warnings.append(f"{where}: longest line has {longest} characters "
                            f"(> {args.max_line}); it will wrap in the PDF")
        if diagram and longest > 150:
            warnings.append(f"{where}: diagram is {longest} characters wide and will overflow")

        if "nocheck" in info[1:] or lang not in CHECKS:
            continue
        checked += 1
        try:
            CHECKS[lang](code)
        except Exception as exc:  # SyntaxError, YAMLError, JSONDecodeError, ...
            detail = str(exc).replace("\n", " ")
            inner = getattr(exc, "lineno", None)
            if inner:
                detail += f" [markdown line {line + inner - 1}]"
            errors.append(f"{where}: {type(exc).__name__}: {detail}")

    total = sum(counts.values())
    summary = ", ".join(f"{k}: {v}" for k, v in counts.most_common())
    print(f"{total} code blocks ({summary})")
    print(f"{checked} parsed, {len(errors)} with errors, {len(warnings)} warnings")
    for w in warnings:
        print(f"WARNING  {w}")
    for e in errors:
        print(f"ERROR    {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
