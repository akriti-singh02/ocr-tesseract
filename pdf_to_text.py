#!/usr/bin/env python3
"""Command-line version of the app: turn PDFs into plain text files.

Examples:
  python pdf_to_text.py book.pdf --lang odia
  python pdf_to_text.py book.pdf --lang hindi,english -o book.txt
  python pdf_to_text.py folder_of_pdfs --lang assamese
  python pdf_to_text.py book.pdf --lang nepali --pages 1-5 --ocr always
  python pdf_to_text.py --list            (show every language)
"""

import argparse
import sys
from pathlib import Path

import pdf_text


def main():
    ap = argparse.ArgumentParser(description="PDF to plain text (Odisha, Assam and Himachal languages).")
    ap.add_argument("input", nargs="?", help="a PDF file, or a folder of PDFs")
    ap.add_argument("--lang", help="language(s), comma separated, e.g. odia or hindi,english")
    ap.add_argument("-o", "--output", help="output .txt (or folder, for a folder of PDFs). "
                                           "Default: next to the PDF, same name, .txt")
    ap.add_argument("--pages", help="only these pages, e.g. 1-5 or 2,4,10-12")
    ap.add_argument("--ocr", choices=["auto", "always", "never"], default="auto",
                    help="auto (default): OCR only scanned/garbled pages; always: OCR every page; "
                         "never: only use the text already in the PDF")
    ap.add_argument("--dpi", type=int, default=300, help="OCR sharpness (default 300; 400 for small print)")
    ap.add_argument("--tesseract", help="full path to tesseract.exe if it is not found automatically")
    ap.add_argument("--list", action="store_true", help="list the languages by state and exit")
    a = ap.parse_args()

    if a.list:
        for state, langs in pdf_text.STATES.items():
            print(f"{state}: " + ", ".join(langs))
        return
    if not a.input or not a.lang:
        ap.error("give a PDF (or folder) and --lang")

    langs = []
    for name in a.lang.split(","):
        lang = pdf_text.find_language(name)
        if not lang:
            sys.exit(f"Unknown language '{name}'. Run with --list to see the choices.")
        langs.append(lang)

    can_ocr = False
    if a.ocr != "never":
        if pdf_text.find_tesseract(a.tesseract):
            missing = set(pdf_text.tesseract_codes(langs).split("+")) - pdf_text.installed_packs()
            if missing:
                sys.exit(f"Tesseract is missing language pack(s): {', '.join(sorted(missing))}. See HOWTO.md.")
            can_ocr = True
        elif a.ocr == "always":
            sys.exit("Tesseract not found. Install it (see HOWTO.md) or pass --tesseract \"path\\to\\tesseract.exe\"")
        else:
            print("Note: Tesseract is not installed, so scanned pages cannot be read. See HOWTO.md.")

    src = Path(a.input)
    if src.is_dir():
        out_dir = Path(a.output) if a.output else src
        out_dir.mkdir(parents=True, exist_ok=True)
        jobs = [(p, out_dir / (p.stem + ".txt")) for p in sorted(src.iterdir()) if p.suffix.lower() == ".pdf"]
    elif src.is_file():
        jobs = [(src, Path(a.output) if a.output else src.with_suffix(".txt"))]
    else:
        sys.exit(f"Not found: {src}")
    if not jobs:
        sys.exit(f"No PDF files in {src}")

    for pdf, out in jobs:
        res = pdf_text.extract(str(pdf), langs, a.pages, a.ocr, a.dpi, can_ocr,
                               progress=lambda d, t: print(f"  page {d}/{t}", end="\r", flush=True))
        out.write_text(pdf_text.to_txt(res), encoding="utf-8-sig")
        counts = {}
        for r in res:
            counts[r["method"]] = counts.get(r["method"], 0) + 1
        how = ", ".join(f"{n} {m}" for m, n in counts.items())
        print(f"\r  {pdf.name}: {len(res)} pages ({how}) -> {out}".ljust(40))


if __name__ == "__main__":
    main()
