# Free alternatives to Tesseract (OCR) and LaBSE (alignment)

Written 2026-10-12 for the DOST languages (English, Hindi, Odia, Assamese, Garo and the other
languages of Odisha, Assam and Himachal Pradesh). This is a desk comparison: none of these models
could be downloaded and tested in the environment where the app was built, so check them on one of
your own PDFs before switching.

First, a reminder: when a PDF already has a text layer (like the SRI booklet), no OCR is used at
all. OCR only matters for scans and for text inside pictures.

## OCR

| Tool | Odia | Assamese / Bengali | Hindi | Runs offline | Cost / licence | Notes |
|---|---|---|---|---|---|---|
| **Tesseract 5 with "best" models** (what the app uses) | yes | yes | yes | yes | free (Apache 2.0) | Covers every script you need. Weak on photos and fancy layouts. The "best" models are more accurate than the "fast" ones; the UB Mannheim installer lets you pick them. |
| **Surya OCR** (Datalab) | check its language list | yes | yes | yes, with a graphics card | code GPL, model free for non-profits / small organisations | Strong on printed pages; the current version needs a separate model server (vLLM or llama.cpp). |
| **Bhashini OCR** (Government of India, from IIIT Hyderabad / AI4Bharat work) | yes | yes | yes | no (online API) | free after registering | Trained on Indian printed documents, usually better than Tesseract on Indic scans. Pages leave your computer. |
| **EasyOCR** | no | Bengali/Assamese yes | yes | yes | free (Apache 2.0) | No Odia, so not enough on its own. |
| **PaddleOCR** | no | limited | yes (Devanagari) | yes | free (Apache 2.0) | Good engine, but no Odia or Assamese models. |
| **IndicPhotoOCR** (IIT Jodhpur, Bharat Scene Text) | yes | yes | yes | yes | free | Made for photos and signboards, not document pages. |
| **Vision-language models** (Qwen-VL, Gemma, olmOCR) | weak | fair | good | yes, needs a GPU | free weights | Read Hindi well; Odia and smaller languages often come out wrong or "translated". |
| **Google Cloud Vision / Document AI** | yes | yes | yes | no | paid after ~1,000 pages a month | Usually the most accurate, but paid and online. |

**My suggestion:** keep Tesseract but make sure the "best" models are installed. If you have a
lot of scanned Odia/Assamese material, try Bhashini OCR (if sending pages online is acceptable)
or Surya (needs a graphics card and some setup) on a few pages and compare.

## Alignment models (what scores "are these two sentences translations?")

| Model | Hindi | Odia | Assamese | Santali, Bodo, Manipuri ... | Garo, Kui, Karbi, Mising ... | Licence | Notes |
|---|---|---|---|---|---|---|---|
| **LaBSE** (what the app uses) | good | good | fair | weak or missing | not trained | Apache 2.0 | Built for exactly this job (finding translation pairs). Solid default. |
| **LASER3 / SONAR** (Meta, from the NLLB project) | good | good | good | several of them covered | not trained | LASER: free; SONAR: non-commercial | Made for mining translation pairs in 200 languages, including Assamese, Odia, Santali, Manipuri. Hard to install on Windows (needs fairseq). |
| **BGE-M3** | good | fair | fair | weak | not trained | MIT | Strong general multilingual model; good second opinion to LaBSE. |
| **multilingual-e5-large** | good | fair | fair | weak | not trained | MIT | Similar to BGE-M3. |
| **L3Cube IndicSBERT** | good | covered | check | no | no | free | Tuned for major Indian languages only. |
| **IndicTrans2 + compare in English** (AI4Bharat) | very good | very good | very good | Santali, Bodo, Manipuri, Dogri, Nepali ... | no | MIT | Translate each sentence to English, then compare. Usually the most accurate for the 22 scheduled languages, but much slower and needs a good computer. |

No free model has been trained on Garo, Kui, Karbi, Mising, Kinnauri and similar languages. For
those, alignment has to lean on sentence length, numbers, names and page/box position, so expect
more rows flagged for review whichever model you use.

**What the app does now:** LaBSE for language pairs it was trained on, and the average of LaBSE and
BGE-M3 for the others (Automatic setting). LASER3 was left out because its Python package needs
fairseq, which does not install on Windows with current Python; SONAR needs fairseq2 (Linux only).
IndicTrans2 is the accuracy ceiling for scheduled languages but needs a strong computer and a
separate setup, so it is not built in either.

**What the app does for OCR:** Tesseract, with the model of each language's script (Odia model for
Odia-script languages, Assamese model for Assamese, Hindi model for Devanagari languages), up to
600 DPI. Surya was left out: its current version runs as a vision-language model that needs a
separate model server (vLLM or llama.cpp) and a graphics card.

## Sources
- [Open-Source OCR Libraries: A Comprehensive Study for Low Resource Language (ICON 2024)](https://preview.aclanthology.org/setup/2024.icon-1.48)
- [Zero-shot OCR Accuracy of Low-Resourced Languages (RANLP 2025)](https://aclanthology.org/2025.ranlp-1.56.pdf)
- [Towards Deployable OCR models for Indic languages](https://arxiv.org/pdf/2205.06740)
- [Bharat Scene Text: dataset and benchmark for Indian scene text](https://arxiv.org/pdf/2511.23071)
- [L3Cube-IndicSBERT](https://arxiv.org/abs/2304.11434v1)
- [How well do embeddings align in low-resource Indian languages? (2026)](https://arxiv.org/abs/2601.10205)
- [NE-Embed: embeddings for Northeast Indian languages](https://app.alphaneural.io/models/MWirelabs/ne-embed)
