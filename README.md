# PDF to dataset

Streamlit app that turns PDFs into monolingual, parallel or multilingual sentence datasets
for the languages of Odisha, Assam and Himachal Pradesh (Tesseract OCR + LaBSE / BGE-M3 alignment).

- **Online (Streamlit Community Cloud):** uses `requirements.txt` and `packages.txt`. OCR works fully;
  alignment uses the offline scorer because the free tier has too little memory for LaBSE / BGE-M3.
- **On your computer:** `pip install -r requirements-full.txt`, then `run_app.bat`
  (or `streamlit run app.py`). `share_app.bat` shares it through a temporary public link.
