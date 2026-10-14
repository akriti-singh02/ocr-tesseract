"""Build a dataset from the text of one or more PDFs.

  monolingual   every sentence of every document, with an id and review flags
  parallel      2 documents with the same content in 2 languages: sentence-by-sentence alignment
  multilingual  3+ documents: each one aligned to document 1 (the pivot), plus one table with a
                row per pivot sentence that found a partner in every language

Alignment uses LaBSE (multilingual sentence embeddings) when sentence-transformers is installed,
otherwise an offline scorer (length + numbers + shared words, then word translations learned
from the confident pairs: IBM Model 1). Every pair gets a similarity score; pairs below the
threshold, merges, differing numbers, wrong script etc. are marked needs_manual_review = Yes.
"""

import io
import zipfile
import regex

import pdf_text
from align import LaBSEScorer, LexicalScorer, MeanScorer, Model1Scorer, align
from clean import garble_score, normalise, script_ratio
from score import review
from segment import split_sentences

# short language codes used in ids and column names (en, or, grt ...)
ISO = {name: v[2] for name, v in pdf_text.LANGUAGES.items()}
# sentence splitting and Unicode clean-up follow the script: Kui in Odia script splits like Odia
SCRIPT_ISO = {"Latin": "en", "Devanagari": "hi", "Oriya": "or", "Bengali": "bn", "Gurmukhi": "pa",
              "Telugu": "te", "Arabic": "ur", "Tibetan": "bo"}

# (a bullet glyph needs no space after it: "•A plant should ...")
BULLET = regex.compile(r"^\s*(?:[•▪●◦➢►✓❋❖]\s*|(?:[\-*>»]|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)]|\(?[ivx]{1,4}\))\s+)")

LIST_START = regex.compile(r"^\s*\(?(?:[A-Za-z]|\d{1,2})[.)]\s")
ITEMS = regex.compile(r"\s+(?=\(?(?:[A-Z]|\d{1,2})[.)]\s+\p{L}{2})")

# ----------------------------------------------------------------------------- sentences
def paragraphs(page_text):
    """Join the lines of a page back into paragraphs; a blank line or a bullet starts a new one."""
    paras, cur = [], []
    lines = []
    for line in page_text.splitlines():                 # "A. APH B. Eclampsia" (form labels): one item per line
        pieces = ITEMS.split(line.strip()) if LIST_START.match(line) else [line]
        lines += pieces if all(regex.search(r"\p{L}{2}", BULLET.sub("", x)) for x in pieces) else [line]
    for line in lines:
        line = line.strip()
        if not line:
            if cur:
                paras.append(" ".join(cur)); cur = []
            continue
        if BULLET.match(line) and cur:
            paras.append(" ".join(cur)); cur = []
        cur.append(BULLET.sub("", line))
    if cur:
        paras.append(" ".join(cur))
    return paras


def is_text(s):
    """At least two letters: drops page numbers, stray symbols and OCR noise."""
    return len(regex.findall(r"\p{L}", s)) >= 2


WORD = regex.compile(r"[(\"'‘“]*[\p{L}\p{M}]{3,}(?:[-'’/(][\p{L}\p{M}]+\)?)*[.,;:!?।)\"'’”]*")


def is_noise(s):
    """OCR of a photo or drawing gives letter soup ("Lei N\\ i f | i h", "୮୮ ୯୯. ୪ ୮ ସା"):
    less than half of the characters are in real words of 3+ letters."""
    tokens = s.split()
    total = sum(len(t) for t in tokens)
    return total == 0 or sum(len(t) for t in tokens if WORD.fullmatch(t)) < 0.5 * total


def sentences(doc_no, lang, pages):
    """pages: output of pdf_text.extract. Returns sentence rows with ids like D1-OR-00012."""
    iso = ISO[lang]
    seg = SCRIPT_ISO.get(pdf_text.LANGUAGES[lang][1], "en")
    rows = []
    for p in pages:
        blocks = p.get("blocks") or [{"text": p["text"], "bbox": None}]
        for bi, b in enumerate(blocks, 1):
            for para in paragraphs(b["text"]):
                for s in split_sentences(normalise(para, seg), seg):
                    if is_text(s) and not (p["method"] == "OCR" and is_noise(s)):
                        rows.append({"sentence_id": f"D{doc_no}-{iso.upper()}-{len(rows) + 1:05d}",
                                     "document_id": f"D{doc_no}", "language": lang, "page": p["page"],
                                     "box": f"{p['page']}.{bi}", "bbox": b["bbox"],
                                     "method": p["method"], "text": s})
    return rows


def review_sentences(rows):
    """Flags for a monolingual sentence list."""
    first = {}
    for r in rows:
        script = pdf_text.LANGUAGES[r["language"]][1]
        s, reasons = r["text"], []
        r["words"] = len(s.split())
        if r["words"] < 3:
            reasons.append("very short (< 3 words)")
        if garble_score(s, script) > 0.05:
            reasons.append("garbled characters")
        if script != "Latin" and regex.search(r"\p{L}{3}", s) and script_ratio(s, script) < 0.5:
            reasons.append(f"not in {script} script")
        key = (r["document_id"], s.strip().lower())
        if key in first:
            reasons.append(f"duplicate of {first[key]}")
        else:
            first[key] = r["sentence_id"]
        r["needs_manual_review"] = "Yes" if reasons else "No"
        r["review_reason"] = "; ".join(reasons)
    return rows


# ----------------------------------------------------------------------------- alignment
def labse_problem():
    """None when the LaBSE / BGE-M3 models can be used; otherwise the error, e.g. "No module named
    'sentence_transformers'" or a version clash between torch / transformers / sentence-transformers."""
    try:
        import sentence_transformers  # noqa: F401
        return None
    except Exception as e:          # a broken install raises more than ImportError
        return f"{type(e).__name__}: {e}"


def labse_available():
    return labse_problem() is None


# Embedding models (free, downloaded once by sentence-transformers): name, model id, review threshold.
# The thresholds are starting points; move the slider if correct pairs keep getting flagged.
MODELS = {"labse": ("LaBSE", "sentence-transformers/LaBSE", 0.6),
          "bge-m3": ("BGE-M3", "BAAI/bge-m3", 0.65)}
OFFLINE_THRESHOLD = 0.4
# languages LaBSE was trained on, among ours (by short code); others get LaBSE + BGE-M3 together
LABSE_LANGS = {"en", "hi", "or", "bn", "pa", "te", "ur", "ne", "mr"}


def model_for(choice, langs):
    """Which model(s) to use for a pair of languages. choice: auto | labse | bge-m3 | both | offline."""
    if choice == "offline" or not labse_available():
        return "offline"
    if choice == "auto":
        return "labse" if all(ISO[l] in LABSE_LANGS for l in langs) else "both"
    return choice


def make_scorer(which):
    """(scorer, name shown to the user, default review threshold)"""
    if which == "offline":
        return LexicalScorer(), "offline (length + numbers + word translations)", OFFLINE_THRESHOLD
    if which == "both":
        parts = [LaBSEScorer(MODELS[k][1]) for k in ("labse", "bge-m3")]
        return MeanScorer(parts), "LaBSE + BGE-M3 (average)", 0.6
    name, model, threshold = MODELS[which]
    return LaBSEScorer(model), name, threshold


def _pair_rows(S, T, scorer, skip=0.3):
    """Align two sentence lists; returns one row per pair (or unpaired sentence)."""
    if not S and not T:
        return []
    if not S or not T:
        path = [(i, 1, 0, 0, None) for i in range(len(S))] + [(0, 0, j, 1, None) for j in range(len(T))]
    else:
        path = align([u["text"] for u in S], [u["text"] for u in T], scorer, skip=skip)
    out = []
    for i, n, j, m, s in path:
        su, tu = S[i:i + n], T[j:j + m]
        out.append({"src": su, "tgt": tu, "alignment": f"{n}-{m}", "score": s})
    return out


def _fill_gaps(rows, scorer, min_score=0.15):
    """An unpaired sentence next to an unpaired sentence of the other language is almost always a
    pair the scorer was unsure about: join them and keep their real score (review will flag it)."""
    out = []
    for r in rows:
        p = out[-1] if out else None
        if p and {p["alignment"], r["alignment"]} == {"1-0", "0-1"}:
            src, tgt = (p, r) if p["alignment"] == "1-0" else (r, p)
            s = scorer([src["src"][0]["text"]], [tgt["tgt"][0]["text"]])
            if s >= min_score:
                out[-1] = {"src": src["src"], "tgt": tgt["tgt"], "alignment": "1-1", "score": s, "by": p["by"]}
                continue
        out.append(r)
    return out


def _same_place(a, b):
    """Two text boxes (page fractions) sit in the same place: they overlap for at least half of the
    smaller one, across and down."""
    ox = min(a[2], b[2]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[1], b[1])
    return (ox > 0 and oy > 0 and ox >= 0.5 * min(a[2] - a[0], b[2] - b[0])
            and oy >= 0.5 * min(a[3] - a[1], b[3] - b[1]))


def _box_groups(S, T):
    """Group the text boxes of one page of each document by position: boxes in the same place are
    linked, and linked boxes (with chains: one box over two smaller ones) form a group.
    Returns [(source sentences, target sentences)] for groups with boxes on both sides, and the
    sentences of boxes left without a partner."""
    sb = list(dict.fromkeys(u["box"] for u in S))
    tb = list(dict.fromkeys(u["box"] for u in T))
    bbox = {("s", u["box"]): u["bbox"] for u in S}
    bbox.update({("t", u["box"]): u["bbox"] for u in T})
    parent = {k: k for k in bbox}

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k
    for x in sb:
        for y in tb:
            if bbox[("s", x)] and bbox[("t", y)] and _same_place(bbox[("s", x)], bbox[("t", y)]):
                parent[root(("t", y))] = root(("s", x))
    groups = {}
    for side, boxes in (("s", sb), ("t", tb)):
        for x in boxes:
            groups.setdefault(root((side, x)), {"s": set(), "t": set()})[side].add(x)
    pairs, rest_s, rest_t = [], [], []
    for g in groups.values():       # dict order = order of the first source box
        gs = [u for u in S if u["box"] in g["s"]]
        gt = [u for u in T if u["box"] in g["t"]]
        if gs and gt:
            pairs.append((gs, gt))
        else:
            rest_s += gs
            rest_t += gt
    return pairs, rest_s, rest_t


def _total(rows):
    return sum(r["score"] or 0 for r in rows if r["src"] and r["tgt"])


def _align_page_by_box(S, T, scorer):
    """Align one page box by box; falls back to the whole page when few sentences sit in boxes
    that match, or when matching the page as one piece fits clearly better (boxes laid out
    differently). Returns (rows, used_boxes)."""
    whole = _pair_rows(S, T, scorer)
    if not S or not T:
        return whole, False
    pairs, rest_s, rest_t = _box_groups(S, T)
    in_boxes = sum(len(gs) + len(gt) for gs, gt in pairs)
    if in_boxes < 0.3 * (len(S) + len(T)):
        return whole, False
    rows = [r for gs, gt in pairs for r in _pair_rows(gs, gt, scorer)]
    rows += _pair_rows(rest_s, rest_t, scorer)
    if _total(whole) > 1.1 * _total(rows):
        return whole, False
    return rows, True


def _align_docs(S, T, scorer, mode):
    """mode: 'box' (page N with page N, box by box), 'page' (page N with page N) or 'document'.
    Every row gets aligned_by = box / page / document."""
    if mode in ("box", "page"):
        pages = sorted({u["page"] for u in S} | {u["page"] for u in T})
        rows = []
        for p in pages:
            ps, pt = [u for u in S if u["page"] == p], [u for u in T if u["page"] == p]
            if mode == "box":
                part, boxed = _align_page_by_box(ps, pt, scorer)
            else:
                part, boxed = _pair_rows(ps, pt, scorer), False
            for r in part:
                r["by"] = "box" if boxed else "page"
            rows += part
    else:
        rows = _pair_rows(S, T, scorer)
        for r in rows:
            r["by"] = "document"
    return _rescue(_fill_gaps(rows, scorer), scorer)


def _rescue(rows, scorer):
    """Sentences left without a partner because the two documents give them in a different order
    (a box read earlier on one page than on the other): on each page, an unpaired sentence and an
    unpaired sentence of the other language are joined when each is the other's best match and the
    score is high. Such pairs get aligned_by '... (out of order)'."""
    need = getattr(scorer, "rescue", 0.75)
    page = lambda r: (r["src"] or r["tgt"])[0]["page"]
    alone_s = [k for k, r in enumerate(rows) if r["src"] and not r["tgt"]]
    alone_t = [k for k, r in enumerate(rows) if r["tgt"] and not r["src"]]
    if not alone_s or not alone_t:
        return rows
    if hasattr(scorer, "prepare"):
        scorer.prepare([rows[k]["src"][0]["text"] for k in alone_s] + [rows[k]["tgt"][0]["text"] for k in alone_t])
    score = {(i, j): scorer([rows[i]["src"][0]["text"]], [rows[j]["tgt"][0]["text"]])
             for i in alone_s for j in alone_t if page(rows[i]) == page(rows[j])}
    best_s, best_t = {}, {}
    for (i, j), v in score.items():
        if v > score.get((i, best_s.get(i)), -1):
            best_s[i] = j
        if v > score.get((best_t.get(j), j), -1):
            best_t[j] = i
    drop = set()
    for i, j in best_s.items():
        if best_t.get(j) == i and score[(i, j)] >= need:
            rows[i] = {"src": rows[i]["src"], "tgt": rows[j]["tgt"], "alignment": "1-1", "score": score[(i, j)],
                       "by": rows[i]["by"] + " (out of order)"}
            drop.add(j)
    return [r for k, r in enumerate(rows) if k not in drop]


def align_pair(S, T, scorer, mode, min_score, a, b, ls, lt):
    """S, T: sentence rows of the two documents; a, b: column prefixes (en, or ...); ls, lt: languages.
    Returns pair rows with ids, score and review flags."""
    if isinstance(scorer, LexicalScorer):
        scorer.fit_ratio([u["text"] for u in S], [u["text"] for u in T])
        first = _align_docs(S, T, scorer, mode)
        good = [(r["src"][0]["text"], r["tgt"][0]["text"]) for r in first
                if r["alignment"] == "1-1" and r["score"] is not None and r["score"] >= 0.55]
        # second pass: word translations learned from the confident pairs of the first pass
        rows = _align_docs(S, T, Model1Scorer(good, base=scorer), mode) if len(good) >= 10 else first
    else:
        rows = _align_docs(S, T, scorer, mode)
    out = []
    for k, r in enumerate(rows, 1):
        su, tu = r["src"], r["tgt"]
        out.append({"pair_id": f"{a.upper()}-{b.upper()}-{k:05d}",
                    f"{a}_sentence_ids": ";".join(u["sentence_id"] for u in su),
                    f"{b}_sentence_ids": ";".join(u["sentence_id"] for u in tu),
                    f"{a}_text": " ".join(u["text"] for u in su),
                    f"{b}_text": " ".join(u["text"] for u in tu),
                    f"{a}_page": su[0]["page"] if su else "", f"{b}_page": tu[0]["page"] if tu else "",
                    "alignment": r["alignment"], "aligned_by": r["by"],
                    "similarity_score": "" if r["score"] is None else round(r["score"], 3),
                    "src_text": " ".join(u["text"] for u in su), "tgt_text": " ".join(u["text"] for u in tu),
                    "score": r["score"]})
    review(out, pdf_text.LANGUAGES[ls][1], pdf_text.LANGUAGES[lt][1], min_score=min_score)
    for r in out:                 # helper columns used by review() only
        del r["src_text"], r["tgt_text"], r["score"]
    return out


def multiway(p, others, pair_tables):
    """p: pivot column prefix; others: prefixes of the other documents.
    One row per pivot sentence (group) that found a partner in every other language."""
    joined = {}
    for t, rows in zip(others, pair_tables):
        for r in rows:
            if r[f"{p}_sentence_ids"] and r[f"{t}_sentence_ids"]:
                joined.setdefault(r[f"{p}_sentence_ids"], {})[t] = r
    out = []
    for ids, parts in joined.items():
        if len(parts) != len(others):
            continue
        first = next(iter(parts.values()))
        row = {"multi_id": f"M-{len(out) + 1:05d}", f"{p}_sentence_ids": ids, f"{p}_text": first[f"{p}_text"]}
        scores, reasons = [], []
        for t in others:
            r = parts[t]
            row[f"{t}_sentence_ids"], row[f"{t}_text"] = r[f"{t}_sentence_ids"], r[f"{t}_text"]
            if r["similarity_score"] != "":
                scores.append(r["similarity_score"])
            if r["review_reason"]:
                reasons.append(f"{t}: {r['review_reason']}")
        row["min_similarity"] = min(scores) if scores else ""
        row["needs_manual_review"] = "Yes" if reasons else "No"
        row["review_reason"] = " | ".join(reasons)
        out.append(row)
    return out


# ----------------------------------------------------------------------------- export
def _cell(v):
    """Excel refuses control characters inside text: drop them."""
    return pdf_text.CONTROL.sub("", v) if isinstance(v, str) else v


def to_xlsx(name, kind, documents, tables, settings):
    """documents: list of dicts; tables: {sheet name: rows}. Rows needing review are shaded."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    lines = [f"Dataset: {name}", f"Type: {kind}", ""] + [f"{k}: {v}" for k, v in settings.items()] + [
        "", "Sheets",
        "Documents: one row per uploaded PDF (document_id D1, D2 ...).",
        "Sentences: every sentence with its id (D1-EN-00001 = document 1, English, sentence 1).",
        "<a>-<b> sheets: sentence-by-sentence alignment of two documents; *_sentence_ids link back to Sentences.",
        "Multilingual: one row per document-1 sentence that has a partner in every language.",
        "", "Columns",
        "alignment: 1-1 = one sentence each side; 1-2 = one sentence matched to two; 1-0 / 0-1 = no partner.",
        "similarity_score: 0-1, how alike the two sides are (higher = more likely a correct translation).",
        "needs_manual_review: Yes = check this row by hand; review_reason says why.",
        "Rows needing review are shaded yellow."]
    for line in lines:
        ws.append([_cell(line)])
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 110
    fill = PatternFill("solid", fgColor="FFF2CC")
    for title, rows in [("Documents", documents)] + list(tables.items()):
        ws = wb.create_sheet(title[:31])
        if not rows:
            ws.append(["(no rows)"])
            continue
        cols = columns(rows)
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append([_cell(r.get(c, "")) for c in cols])
            if r.get("needs_manual_review") == "Yes":
                for c in ws[ws.max_row]:
                    c.fill = fill
        for i, c in enumerate(cols, 1):
            letter = ws.cell(1, i).column_letter
            ws.column_dimensions[letter].width = 60 if c.endswith("text") else 16
            if c.endswith("text"):
                for cell in ws[letter][1:]:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def columns(rows):
    """Every column that appears in any row, in first-seen order."""
    return list(dict.fromkeys(c for r in rows for c in r))


def to_csv(rows):
    import csv
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=columns(rows), restval="")
        w.writeheader()
        w.writerows(rows)
    return "﻿" + buf.getvalue()


def to_zip(name, documents, tables, texts):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{name}/documents.csv", to_csv(documents))
        for title, rows in tables.items():
            z.writestr(f"{name}/{title.lower().replace(' ', '_')}.csv", to_csv(rows))
        for doc_id, txt in texts.items():
            z.writestr(f"{name}/text/{doc_id}.txt", "﻿" + txt)
    return buf.getvalue()


# ----------------------------------------------------------------------------- whole run
def build(kind, docs, model="auto", match="auto", min_score=None, progress=None):
    """kind: 'monolingual' | 'parallel' | 'multilingual'
    docs: [{"name", "language", "pages" (pdf_text.extract output)}], document 1 first.
    model: 'auto' (LaBSE where it knows both languages, else LaBSE + BGE-M3), 'labse', 'bge-m3',
           'both' or 'offline'; falls back to offline when sentence-transformers is not installed.
    min_score: review threshold; None = the default of each model.
    match: 'box' (page N with page N, then text boxes in the same place on the page with each other),
           'page' (page N with page N), 'document' (whole document as one piece), or
           'auto' = box when every document has the same number of pages, otherwise document.
    Returns (documents, tables, settings)."""
    say = progress or (lambda msg: None)
    sents = []
    documents = []
    for k, d in enumerate(docs, 1):
        rows = sentences(k, d["language"], d["pages"])
        sents.append(rows)
        documents.append({"document_id": f"D{k}", "file_name": d["name"], "language": d["language"],
                          "pages": len(d["pages"]),
                          "pages_read_with_ocr": sum(p["method"] == "OCR" for p in d["pages"]),
                          "empty_pages": sum(p["method"] == "empty" for p in d["pages"]),
                          "sentences": len(rows)})
    all_sents = review_sentences([r for rows in sents for r in rows])
    tables = {"Sentences": [{k: r[k] for k in ("sentence_id", "document_id", "language", "page", "box", "text", "words",
                                                "method", "needs_manual_review", "review_reason")}
                            for r in all_sents]}
    settings = {"documents": len(docs)}
    if kind == "monolingual":
        return documents, tables, settings

    same_pages = len({len(d["pages"]) for d in docs}) == 1
    if match == "auto":
        match = "box" if same_pages else "document"
    how = {"box": "page N with page N, box by box", "page": "page N with page N",
           "document": "whole document"}[match]
    if not same_pages and match != "document":
        how += " (the documents have different page counts)"
    settings.update({"matching": how, "pivot (document 1)": docs[0]["language"]})
    pivot = docs[0]["language"]
    isos = [ISO[d["language"]] for d in docs]
    keys = [iso if isos.count(iso) == 1 else f"{iso}{k}" for k, iso in enumerate(isos, 1)]   # column prefixes
    pair_tables = []
    for k in range(1, len(docs)):
        which = model_for(model, [pivot, docs[k]["language"]])
        scorer, scorer_name, default = make_scorer(which)
        threshold = default if min_score is None else min_score
        say(f"Aligning document 1 ({pivot}) with document {k + 1} ({docs[k]['language']}) using {scorer_name}")
        rows = align_pair(sents[0], sents[k], scorer, match, threshold, keys[0], keys[k],
                          pivot, docs[k]["language"])
        pair_tables.append(rows)
        tables[f"{keys[0].upper()}-{keys[k].upper()}"] = rows
        settings[f"model, D1-D{k + 1}"] = scorer_name
        settings[f"review threshold, D1-D{k + 1} (similarity below this = review)"] = threshold
        documents[k]["alignment_model"] = scorer_name
        documents[k]["aligned_pairs_1-1"] = sum(r["alignment"] == "1-1" for r in rows)
        documents[k]["pairs_needing_review"] = sum(r["needs_manual_review"] == "Yes" for r in rows)
        if match == "box":
            documents[k]["pages_aligned_box_by_box"] = len({r[f"{keys[0]}_page"] or r[f"{keys[k]}_page"]
                                                           for r in rows if r["aligned_by"] == "box"})
    if kind == "multilingual":
        tables["Multilingual"] = multiway(keys[0], keys[1:], pair_tables)
    return documents, tables, settings
