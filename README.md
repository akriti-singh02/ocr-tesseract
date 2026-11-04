# PDF to dataset

Streamlit app that turns PDFs into monolingual, parallel or multilingual sentence datasets
for the languages of Odisha, Assam and Himachal Pradesh (Tesseract OCR + LaBSE / BGE-M3 alignment).

- **Online (Streamlit Community Cloud):** uses `requirements.txt` and `packages.txt`. OCR works fully;
  alignment uses the offline scorer because the free tier has too little memory for LaBSE / BGE-M3.
- **On your computer:** `pip install -r requirements-full.txt`, then `run_app.bat`
  (or `streamlit run app.py`). `share_app.bat` shares it through a temporary public link.

## Download

After **Build dataset**, one button downloads `<dataset name>.zip` with everything:

```
my_dataset/my_dataset.xlsx        the workbook
my_dataset/*.csv, text/*.txt      the same data as CSV, plus the extracted text
my_dataset/tables.md              every table in the PDFs, as Markdown: Table 1, Table 2 ...
my_dataset/images.zip             every picture: image_1.png, image_2.png ... in page order
```

`tables.md` and `images.zip` come from [Docling](https://github.com/docling-project/docling) and are
added when it is installed (`python -m pip install -r requirements-docling.txt`, then restart the app;
the sidebar has a switch to turn it off). The first run downloads Docling's models (about 500 MB), so it
does not run on the free Streamlit Community Cloud. The Odia textbooks have no text layer (each line is a
small picture), so Docling finds tables and figures on the rendered page and Tesseract reads the words in
the tables. Pictures repeated on every page (logos, margin icons) are saved once.

Command line, without the app: `python extract_tables_images.py book.pdf -o out` writes
`out/book/tables.md`, `out/book/tables/table_1.md ...` and `out/book/images.zip`.
