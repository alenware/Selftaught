#!/usr/bin/env python3
"""Download the three font families the PDF design uses into assets/fonts/.

Inter (headings/UI), TeX Gyre Pagella (body), DejaVu Sans Mono (code) and
DejaVu Sans (symbol fallback). Standard library only, safe to re-run: files
that already exist are skipped. If a download fails, the script looks for the
same file in the usual Linux system font directories (apt packages
fonts-inter, fonts-texgyre, fonts-dejavu-core) and copies it from there.
"""
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"

INTER_ZIP = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
DEJAVU_ZIP = ("https://github.com/dejavu-fonts/dejavu-fonts/releases/download/"
              "version_2_37/dejavu-fonts-ttf-2.37.zip")
PAGELLA_URL = "https://mirrors.ctan.org/fonts/tex-gyre/opentype/{name}"

INTER = ["Inter-Light.ttf", "Inter-Regular.ttf", "Inter-Italic.ttf", "Inter-Medium.ttf",
         "Inter-SemiBold.ttf", "Inter-Bold.ttf", "Inter-ExtraBold.ttf"]
DEJAVU = ["DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf", "DejaVuSansMono-Oblique.ttf",
          "DejaVuSansMono-BoldOblique.ttf", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"]
PAGELLA = ["texgyrepagella-regular.otf", "texgyrepagella-italic.otf",
           "texgyrepagella-bold.otf", "texgyrepagella-bolditalic.otf"]

SYSTEM_DIRS = [Path("/usr/share/fonts"), Path("/usr/share/texmf/fonts"),
               Path("/usr/local/share/fonts"), Path.home() / ".fonts",
               Path.home() / ".local/share/fonts"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "selftaught-fetch-fonts"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def missing(names):
    return [n for n in names if not (FONTS / n).exists()]


def from_zip(url, names):
    todo = missing(names)
    if not todo:
        return
    zf = zipfile.ZipFile(io.BytesIO(get(url)))
    members = zf.namelist()
    for name in todo:
        # Prefer the static TTF folder when the archive ships several formats.
        hits = sorted((m for m in members if m.rsplit("/", 1)[-1] == name),
                      key=lambda m: ("/ttf/" not in "/" + m, len(m)))
        if not hits:
            raise FileNotFoundError(f"{name} not found inside {url}")
        (FONTS / name).write_bytes(zf.read(hits[0]))
        print(f"  ok  {name}")


def from_ctan():
    for name in missing(PAGELLA):
        (FONTS / name).write_bytes(get(PAGELLA_URL.format(name=name)))
        print(f"  ok  {name}")


def from_system(names):
    for name in missing(names):
        for d in SYSTEM_DIRS:
            hit = next(d.rglob(name), None) if d.exists() else None
            if hit:
                shutil.copy(hit, FONTS / name)
                print(f"  ok  {name} (copied from {hit.parent})")
                break


def main():
    FONTS.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("Inter", INTER, lambda: from_zip(INTER_ZIP, INTER)),
        ("DejaVu", DEJAVU, lambda: from_zip(DEJAVU_ZIP, DEJAVU)),
        ("TeX Gyre Pagella", PAGELLA, from_ctan),
    ]
    for label, names, job in jobs:
        print(label)
        try:
            job()
        except Exception as exc:  # network trouble: fall back to system fonts
            print(f"  download failed ({exc}); looking in system font directories")
            from_system(names)
    left = missing(INTER + DEJAVU + PAGELLA)
    if left:
        print("MISSING: " + ", ".join(left))
        print("Install them (Debian/Ubuntu: sudo apt install fonts-inter fonts-texgyre "
              "fonts-dejavu-core) and run this script again.")
        return 1
    print(f"All fonts present in {FONTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
