# PDF to dataset

Streamlit app that turns PDFs into monolingual, parallel or multilingual sentence datasets
for the languages of Odisha, Assam and Himachal Pradesh (Tesseract OCR + LaBSE / BGE-M3 alignment).

- **Online (Streamlit Community Cloud):** uses `requirements.txt` and `packages.txt`. OCR works fully;
  alignment uses the offline scorer because the free tier has too little memory for LaBSE / BGE-M3.
- **On your computer:** `pip install -r requirements-full.txt`, then `run_app.bat`
  (or `streamlit run app.py`). `share_app.bat` shares it through a temporary public link.

## Tables and pictures (Docling)

`extract_tables_images.py` saves every table in a PDF as its own Markdown file and every picture
as a PNG, numbered in page order, plus a zip of each:

```
python extract_tables_images.py 211_CH_1.pdf -o out
out/211_CH_1/tables/table_1.md, table_2.md ...
out/211_CH_1/images/image_1.png, image_2.png ...
out/211_CH_1/211_CH_1_images.zip, 211_CH_1_tables.zip
```

Install once with `pip install -r requirements-docling.txt` (needs Tesseract with the Odia pack).
The Odia textbooks have no text layer (each line is a small picture), so Docling finds tables and
figures on the rendered page and Tesseract (`--lang ori,eng`) reads the words inside tables.
Pictures repeated on every page (logos, margin icons) are saved once; `--keep-duplicates` keeps all.
