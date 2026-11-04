#!/usr/bin/env python3
"""Pull the tables and pictures out of a PDF with Docling.

For each PDF it writes, in page order:
  <out>/<name>/tables/table_1.md, table_2.md ...   one Markdown table per table found
  <out>/<name>/images/image_1.png, image_2.png ... every picture/figure found
  <out>/<name>/<name>_images.zip                   the images folder, zipped
  <out>/<name>/<name>_tables.zip                   the tables folder, zipped

Docling finds tables and pictures with a layout model that looks at the rendered page, so it
also works on PDFs like the Odia textbooks where every line of text is a small image and the
PDF has no text layer. The words inside tables are read with Tesseract (default: Odia + English).

Examples:
  python extract_tables_images.py book.pdf
  python extract_tables_images.py book.pdf -o out --lang ori,eng
  python extract_tables_images.py folder_of_pdfs --pages 1-5
  python extract_tables_images.py book.pdf --no-ocr     (PDF already has real text)

Needs: pip install docling   (and Tesseract with the language packs, e.g. tesseract-ocr-ori)
"""

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path


def build_converter(langs, ocr=True, scale=2.0):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (PdfPipelineOptions, TableFormerMode,
                                                    TesseractCliOcrOptions)
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_table_structure = True
    opts.table_structure_options.mode = TableFormerMode.ACCURATE
    opts.table_structure_options.do_cell_matching = False  # cells come from OCR, not a text layer
    opts.generate_picture_images = True
    opts.images_scale = scale  # 2.0 = 144 dpi crops
    opts.do_ocr = ocr
    if ocr:
        opts.ocr_options = TesseractCliOcrOptions(lang=langs, force_full_page_ocr=True)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def _page_of(item):
    return item.prov[0].page_no if item.prov else 0


def _zip_folder(folder, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.iterdir(), key=lambda p: (len(p.name), p.name)):
            z.write(f, f.name)


def extract(pdf, out_dir, converter, page_range=None, min_size=40, keep_duplicates=False):
    """Write table_N.md and image_N.png for one PDF. Returns (tables, images) counts."""
    from docling_core.types.doc import PictureItem, TableItem

    kwargs = {"page_range": page_range} if page_range else {}
    doc = converter.convert(str(pdf), **kwargs).document

    tables_dir, images_dir = out_dir / "tables", out_dir / "images"
    for d in (tables_dir, images_dir):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.iterdir():
            old.unlink()

    n_tab = n_img = 0
    seen = set()
    for item, _ in doc.iterate_items():  # reading order = page order
        if isinstance(item, TableItem):
            md = item.export_to_markdown(doc=doc).strip()
            if not md:
                continue
            n_tab += 1
            (tables_dir / f"table_{n_tab}.md").write_text(
                f"<!-- {pdf.name}, page {_page_of(item)} -->\n\n{md}\n", encoding="utf-8")
        elif isinstance(item, PictureItem):
            img = item.get_image(doc)
            if img is None or min(img.size) < min_size:
                continue  # stray specks and lines, not pictures
            key = hashlib.md5(img.convert("RGB").resize((32, 32)).tobytes()).hexdigest()
            if not keep_duplicates and key in seen:
                continue  # same logo/icon repeated on every page
            seen.add(key)
            n_img += 1
            img.save(images_dir / f"image_{n_img}.png")

    _zip_folder(images_dir, out_dir / f"{pdf.stem}_images.zip")
    _zip_folder(tables_dir, out_dir / f"{pdf.stem}_tables.zip")
    return n_tab, n_img


def parse_range(spec):
    if not spec:
        return None
    a, _, b = spec.partition("-")
    return (int(a), int(b or a))


def main():
    ap = argparse.ArgumentParser(description="Save every table (Markdown) and picture (PNG + zip) from PDFs.")
    ap.add_argument("input", help="a PDF file, or a folder of PDFs")
    ap.add_argument("-o", "--output", help="output folder (default: next to the PDF)")
    ap.add_argument("--lang", default="ori,eng", help="Tesseract language packs, comma separated (default ori,eng)")
    ap.add_argument("--pages", help="only these pages, e.g. 3-10")
    ap.add_argument("--no-ocr", action="store_true", help="skip OCR (only for PDFs with a real text layer)")
    ap.add_argument("--scale", type=float, default=2.0, help="image sharpness, 2.0 = 144 dpi (default)")
    ap.add_argument("--keep-duplicates", action="store_true",
                    help="keep pictures repeated on many pages (logos, margin icons)")
    a = ap.parse_args()

    src = Path(a.input)
    if src.is_dir():
        pdfs = sorted(p for p in src.iterdir() if p.suffix.lower() == ".pdf")
    elif src.is_file():
        pdfs = [src]
    else:
        sys.exit(f"Not found: {src}")
    if not pdfs:
        sys.exit(f"No PDF files in {src}")

    converter = build_converter(a.lang.split(","), ocr=not a.no_ocr, scale=a.scale)
    for pdf in pdfs:
        out = Path(a.output) / pdf.stem if a.output else pdf.with_suffix("")
        print(f"{pdf.name}: reading ...", flush=True)
        n_tab, n_img = extract(pdf, out, converter, parse_range(a.pages), keep_duplicates=a.keep_duplicates)
        print(f"{pdf.name}: {n_tab} tables, {n_img} images -> {out}")


if __name__ == "__main__":
    main()
