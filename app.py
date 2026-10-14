"""Streamlit app: PDFs -> sentence dataset (monolingual, parallel or multilingual).

Run:  streamlit run app.py
"""

import hashlib
import io
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

import dataset
import pdf_text

st.set_page_config(page_title="PDF to dataset", page_icon="📄", layout="wide")


@st.cache_resource
def tesseract_status():
    exe = pdf_text.find_tesseract()
    return exe, (pdf_text.installed_packs() if exe else set())


def read_pdf(data, lang, pages, ocr_mode, dpi, can_ocr, progress=None):
    """Read one PDF. Kept for this browser session: building again with other alignment settings,
    or with the same file in another dataset, does not read (or OCR) the PDF a second time."""
    store = st.session_state.setdefault("read_cache", {})
    key = (hashlib.sha1(data).hexdigest(), lang, pages, ocr_mode, dpi, can_ocr)
    if key not in store:
        if len(store) >= 30:
            store.pop(next(iter(store)))
        store[key] = pdf_text.extract(data, [lang], pages, ocr_mode, dpi, can_ocr, progress=progress)
    return store[key]


@st.cache_resource
def labse_ok():
    return dataset.labse_available()


# ------------------------------------------------------------------ sidebar: settings
st.sidebar.title("Settings")
state = st.sidebar.selectbox("State", ["All states"] + list(pdf_text.STATES),
                             help="Only narrows the language lists below. 'All states' shows every language.")
choices = pdf_text.ALL_ORDER if state == "All states" else pdf_text.STATES[state]


def lang_label(lang):
    where = pdf_text.states_of(lang)
    return f"{lang}  ·  {', '.join(where)}" if state == "All states" and where and len(where) < 3 else lang

st.sidebar.subheader("Reading the PDFs")
mode_label = st.sidebar.radio(
    "How to read pages",
    ["Automatic (recommended)", "OCR every page", "Only copy text already in the PDF"],
    help="Automatic copies the text when the PDF has it and uses OCR only for scanned or garbled pages. "
         "Choose 'OCR every page' if the result looks wrong.")
ocr_mode = {"Automatic (recommended)": "auto", "OCR every page": "always",
            "Only copy text already in the PDF": "never"}[mode_label]
pages = st.sidebar.text_input("Pages (optional)", placeholder="e.g. 1-5, 8", help="Leave empty for all pages.")
dpi = st.sidebar.select_slider("OCR sharpness (DPI)", [200, 300, 400, 500, 600], value=300,
                               help="Higher helps with small or faint print (footnotes, tables, poor scans) but "
                                    "is slower: 600 takes about twice as long as 300. For normal-size print 300 is "
                                    "usually as good, because Tesseract reads best when letters are 20-40 pixels tall.")

st.sidebar.subheader("Alignment")
MODEL_CHOICES = {"Automatic (best for each language)": "auto", "LaBSE": "labse", "BGE-M3": "bge-m3",
                 "LaBSE + BGE-M3 (average)": "both", "Offline (no download)": "offline"}
if labse_ok():
    model_label = st.sidebar.selectbox(
        "Alignment model", list(MODEL_CHOICES),
        help="Automatic uses LaBSE when it was trained on both languages (English, Hindi, Odia, Bengali, "
             "Punjabi, Telugu, Urdu, Nepali, Marathi) and the average of LaBSE and BGE-M3 for the others "
             "(Assamese, Garo, Santali ...). Each model is downloaded once (LaBSE about 1.8 GB, BGE-M3 about 2.3 GB).")
    model = MODEL_CHOICES[model_label]
else:
    model = "offline"
    problem = dataset.labse_problem()
    if "No module named 'sentence_transformers'" in problem:
        st.sidebar.warning("LaBSE is not installed, so the much weaker offline scorer is used. This is expected "
                           "on the free online version; for better alignment run the app on a computer that has "
                           "it:\n\n`python -m pip install -r requirements-full.txt`")
    else:
        st.sidebar.warning("LaBSE is installed but cannot start, so the much weaker offline scorer is used. "
                           "Usually a version clash; fix it in a command window, then restart the app:\n\n"
                           "`python -m pip install -U torch sentence-transformers transformers huggingface_hub`"
                           f"\n\nError: {problem}")
own_threshold = st.sidebar.checkbox("Set the review threshold myself", value=False,
                                    help="Off: each model uses its own starting value (LaBSE 0.6, BGE-M3 0.65, "
                                         "average 0.6, offline 0.4).")
threshold = None
if own_threshold:
    threshold = st.sidebar.slider("Needs review below this similarity", 0.0, 1.0, 0.6 if model != "offline" else 0.4,
                                  0.05, help="Pairs with a lower similarity score are marked needs_manual_review = Yes.")
page_anchor = st.sidebar.radio(
    "How to match the documents",
    ["Automatic (recommended)", "Box by box", "Page by page", "Whole document"],
    help="Automatic: when the PDFs have the same number of pages, page N is matched with page N and text "
         "boxes in the same place on the page are aligned with each other (box by box). When the page "
         "counts differ, the whole documents are aligned as one piece.")
match = {"Automatic (recommended)": "auto", "Box by box": "box", "Page by page": "page",
         "Whole document": "document"}[page_anchor]

exe, packs = tesseract_status()
st.sidebar.markdown("---")
if exe:
    st.sidebar.success("Tesseract OCR found")
else:
    st.sidebar.warning("Tesseract is not installed: only PDFs that already contain text will work. "
                       "See HOWTO.md to install it.")

# ------------------------------------------------------------------ step 1: dataset type
st.title("📄 PDF to dataset")
st.write("For the languages of **Odisha, Assam and Himachal Pradesh**. "
         "Answer the questions below, upload the PDFs, then press **Build dataset**.")

st.subheader("1. What kind of dataset are you uploading?")
kind_label = st.radio(
    "Dataset type",
    ["Monolingual: one language", "Parallel: the same content in two languages",
     "Multilingual: the same content in three or more languages"],
    label_visibility="collapsed")
kind = kind_label.split(":")[0].lower()

# ------------------------------------------------------------------ step 2: how many documents
st.subheader("2. How many documents?")
if kind == "parallel":
    n_docs = 2
    st.write("Two documents: one in each language.")
elif kind == "multilingual":
    n_docs = st.number_input("Number of documents (one per language)", min_value=3, max_value=10, value=3)
else:
    n_docs = st.number_input("Number of documents", min_value=1, max_value=20, value=1)

# ------------------------------------------------------------------ step 3: upload
st.subheader("3. Upload the documents")
if kind != "monolingual":
    st.caption("Document 1 is the main document: every other document is aligned to it sentence by sentence. "
               "Put the English (or original) version first.")
default_order = (["English"] if "English" in choices else []) + [c for c in choices if c != "English"]
docs_in = []
cols_per_row = 3
for start in range(0, n_docs, cols_per_row):
    cols = st.columns(cols_per_row)
    for k in range(start, min(n_docs, start + cols_per_row)):
        with cols[k - start]:
            st.markdown(f"**Document {k + 1}**")
            default = choices[0] if kind == "monolingual" else default_order[k % len(default_order)]
            lang = st.selectbox("Language", choices, index=choices.index(default), key=f"lang_{kind}_{state}_{k}",
                                format_func=lang_label, help="Type to search, e.g. 'gar' for Garo.")
            note = pdf_text.LANGUAGES[lang][3]
            if note:
                st.caption(f"{lang}: {note}.")
            f = st.file_uploader("PDF", type=["pdf"], key=f"file_{k}")
            docs_in.append({"language": lang, "file": f})

name = st.text_input("Dataset name (used for file names)", value="my_dataset")
name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip()) or "dataset"

problems = []
if any(d["file"] is None for d in docs_in):
    problems.append("Upload a PDF for every document.")
if kind != "monolingual" and len({d["language"] for d in docs_in}) < len(docs_in):
    problems.append("Parallel and multilingual documents should each be in a different language.")
needed = set()
for d in docs_in:
    needed |= set(pdf_text.tesseract_codes([d["language"]]).split("+"))
missing = sorted(needed - packs) if exe else []
if missing and ocr_mode != "never":
    st.warning(f"Tesseract is missing language pack(s): {', '.join(missing)}. Scanned pages in these "
               "languages cannot be read. See HOWTO.md.")
for p in problems:
    st.info(p)
if kind != "monolingual" and model == "offline" and not labse_ok():
    st.warning("Alignment will use the offline scorer because LaBSE is not available (see the sidebar). "
               "Expect many wrong or unpaired sentences, especially for English with an Indian language.")

# ------------------------------------------------------------------ step 4: build
if st.button("Build dataset", type="primary", disabled=bool(problems)):
    can_ocr = bool(exe) and not missing
    if ocr_mode == "always" and not can_ocr:
        st.error("'OCR every page' needs Tesseract with the language packs above.")
        st.stop()
    docs = []
    with st.status("Building the dataset...", expanded=True) as status:
        for k, d in enumerate(docs_in, 1):
            f = d["file"]
            bar = st.progress(0.0, text=f"Document {k} ({f.name}): reading")
            try:
                res = read_pdf(f.getvalue(), d["language"], pages, ocr_mode, dpi, can_ocr,
                               progress=lambda a, b, k=k, n=f.name: bar.progress(
                                   a / b, text=f"Document {k} ({n}): page {a} of {b}"))
                bar.progress(1.0, text=f"Document {k} ({f.name}): read")
            except Exception as e:             # damaged or password-protected PDF, bad page range
                status.update(label="Stopped", state="error")
                st.error(f"Document {k} ({f.name}) could not be read: {e}")
                st.stop()
            docs.append({"name": f.name, "language": d["language"], "pages": res})
        if kind != "monolingual":
            st.write("Splitting into sentences and aligning" + (" (the first run downloads the model)..."
                                                                 if model != "offline" else "..."))
        try:
            documents, tables, settings = dataset.build(kind, docs, model, match, threshold, progress=st.write)
        except Exception as e:
            status.update(label="Stopped", state="error")
            st.error(f"Alignment failed: {e}")
            st.stop()
        settings = {"dataset type": kind, "state": state, **settings}
        status.update(label="Dataset ready", state="complete", expanded=False)
    st.session_state["out"] = {"name": name, "kind": kind, "documents": documents, "tables": tables,
                               "settings": settings, "texts": {f"D{k}_{Path(d['name']).stem}": pdf_text.to_txt(d["pages"])
                                                               for k, d in enumerate(docs, 1)}}

# ------------------------------------------------------------------ results
out = st.session_state.get("out")
if out:
    st.subheader("4. Your dataset")
    tables, documents = out["tables"], out["documents"]
    main = "Multilingual" if "Multilingual" in tables else next((t for t in tables if t != "Sentences"), "Sentences")
    rows = tables[main]
    flagged = sum(r.get("needs_manual_review") == "Yes" for r in rows)
    c = st.columns(4)
    c[0].metric("Documents", len(documents))
    c[1].metric("Sentences", len(tables["Sentences"]))
    c[2].metric("Rows" if main == "Sentences" else ("Aligned rows" if main == "Multilingual" else "Pairs"), len(rows))
    c[3].metric("Need review", f"{flagged} ({flagged / max(1, len(rows)):.0%})")

    d = st.columns(3)
    d[0].download_button("⬇️ Excel workbook", dataset.to_xlsx(out["name"], out["kind"], documents, tables, out["settings"]),
                         f"{out['name']}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         type="primary")
    d[1].download_button("⬇️ CSV files + text (.zip)", dataset.to_zip(out["name"], documents, tables, out["texts"]),
                         f"{out['name']}.zip", "application/zip")
    with d[2]:
        st.caption(" · ".join(f"{k}: {v}" for k, v in out["settings"].items()))

    only_review = st.checkbox("Show only rows that need review")
    tab_names = ["Documents"] + list(tables) + ["Extracted text"]
    tabs = st.tabs(tab_names)
    with tabs[0]:
        st.dataframe(pd.DataFrame(documents), hide_index=True, use_container_width=True)
    for tab, (title, trows) in zip(tabs[1:], tables.items()):
        with tab:
            df = pd.DataFrame(trows).replace({"": None})   # "" next to numbers confuses the table view
            if only_review and "needs_manual_review" in df:
                df = df[df["needs_manual_review"] == "Yes"]
            if df.empty:
                st.write("No rows.")
                continue
            st.caption(f"{len(df)} rows")
            if "needs_manual_review" in df and len(df) <= 5000:   # shading is slow on very large tables
                df = df.style.apply(lambda r: ["background-color: #fff2cc" if r["needs_manual_review"] == "Yes"
                                               else "" for _ in r], axis=1)
            st.dataframe(df, hide_index=True, use_container_width=True, height=500)
    with tabs[-1]:
        for doc_id, txt in out["texts"].items():
            with st.expander(doc_id):
                st.text(txt[:20000] + ("\n... (download the .zip for the full text)" if len(txt) > 20000 else ""))
