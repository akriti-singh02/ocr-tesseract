#!/usr/bin/env python3
"""Pull the tables and pictures out of a PDF with Docling.

Used by the Streamlit app (app.py: tables.md and images.zip go into the download zip) and from
the command line. For each PDF the command line writes, in page order:
  <out>/<name>/tables.md                     every table, as Markdown, numbered Table 1, Table 2 ...
  <out>/<name>/tables/table_1.md, ...        the same tables, one file each
  <out>/<name>/images.zip                    image_1.png, image_2.png ... every picture/figure

Docling finds tables and pictures with a layout model that looks at the rendered page, so it
also works on PDFs like the Odia textbooks where every line of text is a small image and the
PDF has no text layer. The words inside tables are read with Tesseract (default: Odia + English).

Examples:
  python extract_tables_images.py book.pdf
  python extract_tables_images.py book.pdf -o out --lang ori,eng
  python extract_tables_images.py folder_of_pdfs --pages 1-5
  python extract_tables_images.py book.pdf --no-ocr     (PDF already has real text)

Needs: pip install -r requirements-docling.txt   (and Tesseract with the language packs)
The first run downloads Docling's layout and table models from huggingface.co.
"""

import argparse
import hashlib
import io
import sys
import zipfile
from pathlib import Path


def available():
    """True when Docling is installed."""
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def build_converter(langs=("ori", "eng"), ocr=True, scale=2.0):
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
        opts.ocr_options = TesseractCliOcrOptions(lang=list(langs), force_full_page_ocr=True)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def find(pdf, converter, name="document.pdf", pages=None, min_size=40, keep_duplicates=False):
    """Tables and pictures of one PDF, in page order.
    pdf: path or bytes. pages: set of page numbers (1-based) to keep, None = all.
    Returns (tables, images): tables = [{"page", "markdown"}], images = [{"page", "image" (PIL)}]."""
    from docling.datamodel.base_models import DocumentStream
    from docling_core.types.doc import PictureItem, TableItem

    source = DocumentStream(name=name, stream=io.BytesIO(pdf)) if isinstance(pdf, bytes) else str(pdf)
    kwargs = {"page_range": (min(pages), max(pages))} if pages else {}
    doc = converter.convert(source, **kwargs).document

    tables, images, seen = [], [], set()
    for item, _ in doc.iterate_items():  # reading order = page order
        page = item.prov[0].page_no if getattr(item, "prov", None) else 0
        if pages and page not in pages:
            continue
        if isinstance(item, TableItem):
            md = item.export_to_markdown(doc=doc).strip()
            if md:
                tables.append({"page": page, "markdown": md})
        elif isinstance(item, PictureItem):
            img = item.get_image(doc)
            if img is None or min(img.size) < min_size:
                continue  # stray specks and lines, not pictures
            key = hashlib.md5(img.convert("RGB").resize((32, 32)).tobytes()).hexdigest()
            if not keep_duplicates and key in seen:
                continue  # same logo/icon repeated on every page
            seen.add(key)
            images.append({"page": page, "image": img})
    return tables, images


def tables_markdown(tables, title="Tables"):
    """One Markdown file holding every table. tables: [{"page", "markdown", optional "source"}]."""
    if not tables:
        return f"# {title}\n\nNo tables found.\n"
    parts = [f"# {title}\n"]
    for n, t in enumerate(tables, 1):
        where = f"{t['source']}, page {t['page']}" if t.get("source") else f"page {t['page']}"
        parts.append(f"## Table {n}\n\n<!-- {where} -->\n\n{t['markdown']}\n")
    return "\n".join(parts)


def images_zip(images):
    """Zip (bytes) with image_1.png, image_2.png ... in the given order."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, im in enumerate(images, 1):
            png = io.BytesIO()
            im["image"].save(png, format="PNG")
            z.writestr(f"image_{n}.png", png.getvalue())
    return buf.getvalue()


def save(pdf, out_dir, converter, pages=None, keep_duplicates=False):
    """Command-line output for one PDF. Returns (tables, images) counts."""
    tables, images = find(pdf, converter, pdf.name, pages, keep_duplicates=keep_duplicates)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tables.md").write_text(tables_markdown(tables, pdf.name), encoding="utf-8")
    one_by_one = out_dir / "tables"
    one_by_one.mkdir(exist_ok=True)
    for old in one_by_one.glob("table_*.md"):
        old.unlink()
    for n, t in enumerate(tables, 1):
        (one_by_one / f"table_{n}.md").write_text(f"<!-- {pdf.name}, page {t['page']} -->\n\n{t['markdown']}\n",
                                                 encoding="utf-8")
    (out_dir / "images.zip").write_bytes(images_zip(images))
    return len(tables), len(images)


def parse_range(spec):
    if not spec:
        return None
    a, _, b = spec.partition("-")
    return set(range(int(a), int(b or a) + 1))


def main():
    ap = argparse.ArgumentParser(description="Save every table (Markdown) and picture (PNG in a zip) from PDFs.")
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
        n_tab, n_img = save(pdf, out, converter, parse_range(a.pages), a.keep_duplicates)
        print(f"{pdf.name}: {n_tab} tables, {n_img} images -> {out}")


if __name__ == "__main__":
    main()
