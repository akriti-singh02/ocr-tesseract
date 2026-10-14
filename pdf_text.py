"""PDF -> text for the languages of Odisha, Assam and Himachal Pradesh.

Used by both the Streamlit app (app.py) and the command line (pdf_to_text.py).

Two ways of reading a page, picked automatically:
  text layer  the PDF already holds the text: copy it. Old Hindi/Odia fonts
              (Kruti Dev, Walkman-Chanakya, Sarala) are converted to Unicode.
  OCR         the page is a scan/photo or its text is gibberish: Tesseract reads it.
"""

import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymupdf as fitz
import pytesseract
import regex
from PIL import Image, ImageOps

from legacy_fonts import convert_spans, english_share, font_map, script_share

# Every language: name -> (Tesseract language pack, Unicode script, short code for ids, note).
# Most languages of the three states have no OCR model of their own: they are read with the model
# of the script they are written in (Garo and Karbi in Roman script -> English model, Kui in Odia
# script -> Odia model ...). Text already inside a PDF is copied whatever the language.
_ROMAN, _ODIA, _DEVA, _BENG = ("eng", "Latin"), ("ori", "Oriya"), ("hin", "Devanagari"), ("asm", "Bengali")


def _lang(model, code, note=""):
    return (model[0], model[1], code, note)


LANGUAGES = {
    # main languages (own OCR model)
    "English": ("eng", "Latin", "en", ""),
    "Hindi": ("hin", "Devanagari", "hi", ""),
    "Odia": ("ori", "Oriya", "or", ""),
    "Assamese": ("asm", "Bengali", "as", ""),
    "Bengali": ("ben", "Bengali", "bn", ""),
    "Telugu": ("tel", "Telugu", "te", ""),
    "Sanskrit": ("san", "Devanagari", "sa", ""),
    "Nepali": ("nep", "Devanagari", "ne", ""),
    "Punjabi": ("pan", "Gurmukhi", "pa", ""),
    "Urdu": ("urd", "Arabic", "ur", ""),
    "Tibetan": ("bod", "Tibetan", "bo", ""),
    # Odisha
    "Sambalpuri / Kosli": _lang(_ODIA, "spv", "Odia script, read with the Odia model"),
    "Desia": _lang(_ODIA, "dso", "Odia script, read with the Odia model"),
    "Santali (Odia script)": _lang(_ODIA, "sat", "read with the Odia model; Ol Chiki script cannot be read"),
    "Santali (Devanagari)": _lang(_DEVA, "sat", "read with the Hindi model; Ol Chiki script cannot be read"),
    "Santali (Roman script)": _lang(_ROMAN, "sat", "read with the English model; Ol Chiki script cannot be read"),
    "Ho (Odia script)": _lang(_ODIA, "hoc", "read with the Odia model; Warang Citi script cannot be read"),
    "Ho (Devanagari)": _lang(_DEVA, "hoc", "read with the Hindi model; Warang Citi script cannot be read"),
    "Mundari (Odia script)": _lang(_ODIA, "unr", "read with the Odia model"),
    "Mundari (Devanagari)": _lang(_DEVA, "unr", "read with the Hindi model"),
    "Kui": _lang(_ODIA, "kxu", "Odia script, read with the Odia model"),
    "Kuvi": _lang(_ODIA, "kxv", "Odia script, read with the Odia model"),
    "Saora / Sora": _lang(_ODIA, "srb", "Odia script, read with the Odia model; Sorang Sompeng cannot be read"),
    "Kharia": _lang(_ODIA, "khr", "Odia script, read with the Odia model"),
    "Juang": _lang(_ODIA, "jun", "Odia script, read with the Odia model"),
    "Kisan": _lang(_ODIA, "xis", "Odia script, read with the Odia model"),
    "Kurukh / Oraon (Odia script)": _lang(_ODIA, "kru", "read with the Odia model"),
    "Kurukh / Oraon (Devanagari)": _lang(_DEVA, "kru", "read with the Hindi model"),
    "Gondi (Odia script)": _lang(_ODIA, "gon", "read with the Odia model"),
    "Gondi (Devanagari)": _lang(_DEVA, "gon", "read with the Hindi model"),
    "Bonda / Remo": _lang(_ODIA, "bfw", "Odia script, read with the Odia model"),
    "Gadaba": _lang(_ODIA, "gbj", "Odia script, read with the Odia model"),
    "Bhumij": _lang(_ODIA, "bhu", "Odia script, read with the Odia model"),
    # Assam
    "Bodo": _lang(_DEVA, "brx", "Devanagari, read with the Hindi model"),
    "Garo": _lang(_ROMAN, "grt", "Roman script, read with the English model"),
    "Karbi": _lang(_ROMAN, "mjw", "Roman script, read with the English model"),
    "Mising": _lang(_ROMAN, "mrg", "Roman script, read with the English model"),
    "Dimasa": _lang(_ROMAN, "dis", "Roman script, read with the English model"),
    "Rabha (Roman script)": _lang(_ROMAN, "rah", "read with the English model"),
    "Rabha (Assamese script)": _lang(_BENG, "rah", "read with the Assamese model"),
    "Tiwa": _lang(_ROMAN, "lax", "Roman script, read with the English model"),
    "Deori (Assamese script)": _lang(_BENG, "der", "read with the Assamese model"),
    "Deori (Roman script)": _lang(_ROMAN, "der", "read with the English model"),
    "Hmar": _lang(_ROMAN, "hmr", "Roman script, read with the English model"),
    "Thadou Kuki": _lang(_ROMAN, "tcz", "Roman script, read with the English model"),
    "Khasi": _lang(_ROMAN, "kha", "Roman script, read with the English model"),
    "Rengma Naga": _lang(_ROMAN, "nre", "Roman script, read with the English model"),
    "Zeme Naga": _lang(_ROMAN, "nzm", "Roman script, read with the English model"),
    "Sylheti": _lang(("ben", "Bengali"), "syl", "Bengali script, read with the Bengali model"),
    "Manipuri (Bengali script)": _lang(("ben", "Bengali"), "mni", "read with the Bengali model; Meitei Mayek cannot be read"),
    "Sadri": _lang(_DEVA, "sck", "Devanagari, read with the Hindi model"),
    # Himachal Pradesh
    "Kangri": _lang(_DEVA, "xnr", "Devanagari, read with the Hindi model"),
    "Mandeali": _lang(_DEVA, "mjl", "Devanagari, read with the Hindi model"),
    "Kullui": _lang(_DEVA, "kfx", "Devanagari, read with the Hindi model"),
    "Chambeali": _lang(_DEVA, "cdh", "Devanagari, read with the Hindi model"),
    "Mahasui": _lang(_DEVA, "bfz", "Devanagari, read with the Hindi model"),
    "Sirmauri": _lang(_DEVA, "srx", "Devanagari, read with the Hindi model"),
    "Bilaspuri / Kahluri": _lang(_DEVA, "kfs", "Devanagari, read with the Hindi model"),
    "Gaddi": _lang(_DEVA, "gbk", "Devanagari, read with the Hindi model"),
    "Kinnauri": _lang(_DEVA, "kfk", "Devanagari, read with the Hindi model"),
    "Lahauli": _lang(_DEVA, "lae", "Devanagari, read with the Hindi model"),
    "Spiti Bhoti": _lang(("bod", "Tibetan"), "sbu", "Tibetan script, read with the Tibetan model"),
    "Dogri": _lang(_DEVA, "doi", "Devanagari, read with the Hindi model"),
}

STATES = {
    "Odisha": ["Odia", "English", "Hindi", "Sambalpuri / Kosli", "Desia", "Santali (Odia script)",
               "Santali (Devanagari)", "Santali (Roman script)", "Ho (Odia script)", "Ho (Devanagari)",
               "Mundari (Odia script)", "Mundari (Devanagari)", "Kui", "Kuvi", "Saora / Sora", "Kharia",
               "Juang", "Kisan", "Kurukh / Oraon (Odia script)", "Kurukh / Oraon (Devanagari)",
               "Gondi (Odia script)", "Gondi (Devanagari)", "Bonda / Remo", "Gadaba", "Bhumij",
               "Bengali", "Telugu", "Urdu", "Sanskrit"],
    "Assam": ["Assamese", "English", "Hindi", "Bodo", "Garo", "Karbi", "Mising", "Dimasa",
              "Rabha (Roman script)", "Rabha (Assamese script)", "Tiwa", "Deori (Assamese script)",
              "Deori (Roman script)", "Hmar", "Thadou Kuki", "Khasi", "Rengma Naga", "Zeme Naga",
              "Santali (Roman script)", "Sadri", "Bengali", "Sylheti", "Manipuri (Bengali script)", "Nepali"],
    "Himachal Pradesh": ["Hindi", "English", "Kangri", "Mandeali", "Kullui", "Chambeali", "Mahasui",
                         "Sirmauri", "Bilaspuri / Kahluri", "Gaddi", "Kinnauri", "Lahauli", "Spiti Bhoti",
                         "Tibetan", "Punjabi", "Dogri", "Nepali", "Sanskrit", "Urdu"],
}
# the order used when "All states" is picked: the main languages first
ALL_ORDER = ["English", "Hindi", "Odia", "Assamese", "Garo"] + sorted(
    l for l in LANGUAGES if l not in ("English", "Hindi", "Odia", "Assamese", "Garo"))
assert set(ALL_ORDER) == set(LANGUAGES) and all(l in LANGUAGES for v in STATES.values() for l in v)


def states_of(lang):
    return [s for s, langs in STATES.items() if lang in langs]


ALIASES = {"hi": "Hindi", "hin": "Hindi", "or": "Odia", "ori": "Odia", "oriya": "Odia", "odi": "Odia",
           "as": "Assamese", "asm": "Assamese", "assami": "Assamese", "en": "English", "eng": "English",
           "bn": "Bengali", "ben": "Bengali", "bangla": "Bengali", "te": "Telugu", "tel": "Telugu",
           "sa": "Sanskrit", "san": "Sanskrit", "ne": "Nepali", "nep": "Nepali",
           "pa": "Punjabi", "pan": "Punjabi", "ur": "Urdu", "urd": "Urdu", "bo": "Tibetan", "bod": "Tibetan",
           "bhoti": "Spiti Bhoti", "santali": "Santali (Odia script)", "ho": "Ho (Odia script)",
           "mundari": "Mundari (Odia script)", "kurukh": "Kurukh / Oraon (Devanagari)",
           "oraon": "Kurukh / Oraon (Devanagari)", "gondi": "Gondi (Devanagari)", "sora": "Saora / Sora",
           "saora": "Saora / Sora", "sambalpuri": "Sambalpuri / Kosli", "kosli": "Sambalpuri / Kosli",
           "bonda": "Bonda / Remo", "rabha": "Rabha (Roman script)", "deori": "Deori (Assamese script)",
           "kuki": "Thadou Kuki", "thadou": "Thadou Kuki", "manipuri": "Manipuri (Bengali script)",
           "meitei": "Manipuri (Bengali script)", "bilaspuri": "Bilaspuri / Kahluri", "kahluri": "Bilaspuri / Kahluri",
           "pahari": "Kangri"}
for _name, (_m, _s, _code, _n) in LANGUAGES.items():
    ALIASES.setdefault(_code, _name)


WINDOWS_TESSERACT = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def find_language(name):
    """'odia', 'or', 'Odia' -> 'Odia'; None if unknown."""
    key = name.strip().lower()
    for lang in LANGUAGES:
        if lang.lower() == key:
            return lang
    return ALIASES.get(key)


def find_tesseract(path=None):
    """Point pytesseract at the Tesseract program. Returns its path, or None if not installed."""
    if path:
        exe = path if os.path.isfile(path) else None
    else:
        exe = shutil.which("tesseract") or next((p for p in WINDOWS_TESSERACT if os.path.isfile(p)), None)
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    return exe


def installed_packs():
    return set(pytesseract.get_languages(config=""))


def tesseract_codes(langs):
    """['Odia', 'English'] -> 'ori+eng' (no repeats, English always added for mixed pages)."""
    codes = []
    for lang in langs + ["English"]:
        code = LANGUAGES[lang][0]
        if code not in codes:
            codes.append(code)
    return "+".join(codes)


def parse_pages(spec, count):
    """'1-5,8' -> [0, 1, 2, 3, 4, 7] (0-based); empty -> every page."""
    if not spec or not spec.strip():
        return list(range(count))
    pages = set()
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        pages.update(range(int(a), int(b or a) + 1))
    return [p - 1 for p in sorted(pages) if 1 <= p <= count]


def looks_readable(text, scripts):
    """True when the copied page text is real text in one of the expected scripts."""
    letters = regex.findall(r"\p{L}", text)
    if len(letters) < 30:                       # (almost) no text: a scan or a picture
        return False
    allowed = "".join(rf"\p{{Script={s}}}" for s in scripts if s != "Latin")
    # Broken old-style fonts that came out "almost Unicode": letters from other alphabets
    # (Ø, Ę, ā ...), or words that start with a vowel sign
    odd = sum(1 for c in letters if not regex.match(rf"[{allowed}A-Za-z]", c))
    words = text.split()
    mark_first = sum(1 for w in words if regex.match(r"\p{M}", w))
    if odd / len(letters) > 0.02 or mark_first / max(len(words), 1) > 0.03:
        return False
    if scripts == ["Latin"]:
        return script_share(text, "Latin") > 0.8
    indic = sum(script_share(text, s) for s in scripts if s != "Latin")
    # mostly the expected script, or mostly real English words (an English page in the book)
    return indic > 0.5 or english_share(text) > 0.15


LATIN_WORD = regex.compile(r"[A-Za-z]")
# pages OCR'd at the same time (each uses one CPU core); 4 suits most laptops
OCR_WORKERS = max(1, min(4, (os.cpu_count() or 2) - 1))
MIN_LINE_CONF = 50       # lines whose middle word confidence is lower are dropped (photo noise)
MIN_INSERTED_CONF = 75
TRUSTED_LATIN = 85        # Tesseract confidence above which an English word in an Indic page is kept


OPEN_END = regex.compile(r"[^.?!।॥:;]$")
STARTS_LIST = regex.compile(r"^\s*(?:[•▪●◦➢►✓\-*]|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)])\s")


def page_blocks(page, fonts):
    """Text layer of a page as a list of {"text", "bbox"} text boxes in reading order (bbox as
    fractions of the page width/height); spans in an old-style font are converted to Unicode, dingbat bullets become "•".
    A block that stops mid-sentence is joined with the next block when that one continues it
    directly below (PDFs often cut one paragraph into several blocks)."""
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        lines = [convert_spans(l["spans"], fonts) for l in b.get("lines", [])]
        text = "\n".join(l.strip() for l in lines if l.strip())
        if not text:
            continue
        sizes = [sp["size"] for l in b["lines"] for sp in l["spans"] if sp["text"].strip()]
        size = max(sizes) if sizes else 10
        p = blocks[-1] if blocks else None
        if (p and OPEN_END.search(p["text"]) and not STARTS_LIST.match(text) and abs(p["size"] - size) < 0.6
                and (text[:1].islower() or not (text[:1].isupper() or text[:1].isdigit()))
                and min(p["bbox"][2], b["bbox"][2]) > max(p["bbox"][0], b["bbox"][0])      # same column
                and 0 <= b["bbox"][1] - p["bbox"][3] <= 1.8 * size):                        # right below
            p["text"] += "\n" + text
            p["bbox"] = (min(p["bbox"][0], b["bbox"][0]), p["bbox"][1], max(p["bbox"][2], b["bbox"][2]), b["bbox"][3])
            continue
        blocks.append({"text": text, "bbox": b["bbox"], "size": size})
    W, H = page.rect.width or 1, page.rect.height or 1
    return [{"text": b["text"], "bbox": _norm(b["bbox"], W, H)} for b in blocks]


def _norm(bbox, W, H):
    return tuple(round(v, 4) for v in (bbox[0] / W, bbox[1] / H, bbox[2] / W, bbox[3] / H))


def page_text(page, fonts):
    return "\n\n".join(b["text"] for b in page_blocks(page, fonts))


WEB = regex.compile(r"www\.|https?:|\w@\w|\w\.(?:in|com|org|net|gov|nic)\b", regex.I)


def _read_lines(img, codes, psm, offset=(0, 0)):
    """Tesseract words grouped into lines, in reading order: [{key, top, bottom, words}],
    each word (text, confidence, x, y, w, h). offset: where img sits on the page (for crops)."""
    d = pytesseract.image_to_data(img, lang=codes, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    d["left"] = [x + offset[0] for x in d["left"]]
    d["top"] = [y + offset[1] for y in d["top"]]
    lines = {}
    for i, word in enumerate(d["text"]):
        if not word.strip():
            continue
        key = (psm, offset[1], d["block_num"][i], d["par_num"][i], d["line_num"][i])
        box = (d["left"][i], d["top"][i], d["width"][i], d["height"][i])
        line = lines.setdefault(key, {"key": key, "top": box[1], "bottom": box[1] + box[3],
                                      "right": box[0] + box[2], "words": []})
        line["top"], line["bottom"] = min(line["top"], box[1]), max(line["bottom"], box[1] + box[3])
        line["right"] = max(line["right"], box[0] + box[2])
        line["words"].append((word.strip(), float(d["conf"][i])) + box)
    return list(lines.values())


def _overlaps(a, b):
    """Two word boxes (x, y, w, h) overlap by more than half of the smaller one."""
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w > 0 and h > 0 and w * h > 0.5 * min(a[2] * a[3], b[2] * b[3])


def _missing_lines(lines, extra):
    """Lines found by a second Tesseract pass that the first pass skipped entirely (text inside
    boxes, frames or coloured bands is often dropped by the page-layout step)."""
    boxes = [w[2:] for l in lines for w in l["words"]]
    out = []
    for l in extra:
        found = sum(any(_overlaps(w[2:], b) for b in boxes) for w in l["words"])
        if found < 0.5 * len(l["words"]) and regex.search(r"\p{L}{2}", " ".join(w[0] for w in l["words"])):
            l["inserted"] = True
            out.append(l)
    return out


def _runs(mask, length, axis):
    """Pixels that belong to a straight run of at least `length` ink pixels along `axis`."""
    import numpy as np
    m = mask if axis == 1 else mask.T
    c = np.cumsum(np.pad(m, ((0, 0), (1, 0))).astype(np.int32), axis=1)
    full = (c[:, length:] - c[:, :-length]) == length          # window starting at x is all ink
    out = np.zeros_like(m)
    for k in range(length):                                     # spread each full window over its pixels
        out[:, k:k + full.shape[1]] |= full
    return out if axis == 1 else out.T


def _segments(row):
    """(start, end) of each run of True in a 1-D bool array."""
    import numpy as np
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    return zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))


def _keep_lines(runs, paper):
    """Keep the runs (along rows) that have paper on both sides for most of their length; a band
    of colour between two lines of white text does not."""
    import numpy as np
    out = np.zeros_like(runs)
    for y in np.flatnonzero(runs.any(axis=1)):
        for x0, x1 in _segments(runs[y]):
            if paper[y, x0:x1].mean() >= 0.6:
                out[y, x0:x1] = True
    return out


def upright(img):
    """Turn a page whose text runs sideways (landscape content printed on a portrait page) the right
    way up, using Tesseract's orientation detection. Upside-down guesses are ignored: on upright
    Odia and other Indic pages Tesseract often wrongly says "upside down"."""
    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
    except Exception:                                         # too little text, or no osd model installed
        return img
    if osd.get("rotate") in (90, 270) and float(osd.get("orientation_conf", 0)) >= 3:
        return img.rotate(-osd["rotate"], expand=True, fillcolor="white")
    return img


def clear_form_marks(img):
    """Paint out what makes Tesseract write "[ |", "| |" or lose whole lines on forms:
    - empty (or ticked) square checkboxes: a closed square about one to three letters tall with
      nothing inside but a tick;
    - table grid lines: long horizontal rules, and vertical rules that meet one of them.
    Letters are left alone: a letter never forms a closed empty square, and its strokes are shorter
    than a rule. Returns a new picture (the same one when nothing was found)."""
    import numpy as np
    gray = np.array(img.convert("L"))
    ink = gray < 160
    H, W = ink.shape
    erase = np.zeros_like(ink)
    smallest, largest = max(12, W // 120), max(40, W // 12)
    horiz = _runs(ink, smallest, 1)
    done = np.zeros_like(ink)
    for y in np.flatnonzero(horiz.any(axis=1)):
        for x0, x1 in _segments(horiz[y]):
            s = x1 - x0
            if s > largest or done[y, x0:x1].any():
                continue
            def depth(xs):                                    # ink straight down from row y
                best = 0
                for x in xs:
                    col = ink[y:min(H, y + 2 * s), x]
                    best = max(best, int(np.argmin(col)) if not col.all() else len(col))
                return best
            left, right = depth(range(max(0, x0 - 1), min(W, x0 + 3))), depth(range(max(0, x1 - 3), min(W, x1 + 1)))
            h = min(left, right)
            if not (0.75 * s <= h <= 1.35 * s) or abs(left - right) > 0.1 * h + 2:
                continue
            col = ink[y:y + h, (x0 + x1) // 2]
            if np.argmin(col) > max(2, s // 6):
                continue                                      # thick stroke for its size: part of a letter (B)
            band_l = ink[y + 2:y + h - 2, max(0, x0 - 6):x0 + 7]
            band_r = ink[y + 2:y + h - 2, x1 - 6:min(W, x1 + 7)]
            if not band_l.any(axis=1).all() or not band_r.any(axis=1).all():
                continue
            outer_l = band_l.argmax(axis=1)                   # outermost ink on each row, each side
            outer_r = band_r.shape[1] - 1 - band_r[:, ::-1].argmax(axis=1)
            if np.ptp(outer_l) > 1 or np.ptp(outer_r) > 1 or outer_l.min() == 0 or outer_r.max() == band_r.shape[1] - 1:
                continue                                      # a side is not a lone straight line: a letter (B, O, D)
            bottom = horiz[max(0, y + h - 4):y + h + 2, x0 + 3:x1 - 3]
            if bottom.size == 0 or bottom.any(axis=0).mean() < 0.8:
                continue                                      # no bottom edge: a letter like "П" or "T"
            above = ink[max(0, y - 4):max(0, y - 1), max(0, x0 - 2):x1 + 2]
            below = ink[y + h + 1:y + h + 4, max(0, x0 - 2):x1 + 2]
            if (above.size and above.mean() > 0.1) or (below.size and below.mean() > 0.1):
                continue                                      # strokes go on above or below: the bowl of a B
            t = max(3, s // 6)
            inside = ink[y + t:y + h - t, x0 + t:x1 - t]
            if inside.size and inside.mean() > 0.15:
                continue                                      # something written inside: a table cell
            erase[max(0, y - 2):y + h + 2, max(0, x0 - 2):x1 + 2] = True
            done[max(0, y - 2):y + h + 2, max(0, x0 - 2):x1 + 2] = True
    thin = max(6, H // 400)                                   # a rule is a line, not a coloured band
    rules = _runs(ink, max(60, W // 8), 1)                     # long horizontal rules
    rules &= ~_runs(rules, thin + 1, 0)
    d = thin + 2
    paper = np.zeros_like(ink)                                # paper on both sides, d pixels away
    paper[d:-d] = ~ink[:-2 * d] & ~ink[2 * d:]
    rules = _keep_lines(rules, paper)
    if rules.any():
        near = rules.copy()
        for k in range(1, 5):                                 # rows within 4 px of a rule
            near[k:] |= rules[:-k]
            near[:-k] |= rules[k:]
        tall = _runs(ink, max(30, W // 40), 0)
        tall &= ~_runs(tall, thin + 1, 1)
        paper = np.zeros_like(ink)
        paper[:, d:-d] = ~ink[:, :-2 * d] & ~ink[:, 2 * d:]
        tall = _keep_lines(tall.T, paper.T).T
        lines = rules.copy()
        for x in np.flatnonzero(tall.any(axis=0)):
            for y0, y1 in _segments(tall[:, x]):
                if near[y0, x] or near[y1 - 1, x]:            # a vertical rule that meets a horizontal one
                    lines[y0:y1, x] = True
        spread = lines.copy()                                 # with the grey, anti-aliased edge of each line
        for k in (1, 2, 3):
            spread[k:] |= lines[:-k]
            spread[:-k] |= lines[k:]
            spread[:, k:] |= lines[:, :-k]
            spread[:, :-k] |= lines[:, k:]
        erase |= spread & (gray < 230)
    if not erase.any():
        return img
    out = np.array(img.convert("RGB"))
    out[erase] = 255
    return Image.fromarray(out)


def _read_piece(g, codes, left, top, typical, depth=0):
    """Read one cut-out line (grayscale array g at page position left, top). Tesseract sometimes
    returns nothing for a long line it reads fine in halves: then it is split at the widest blank
    gap near the middle and each half is read."""
    import numpy as np
    m = typical // 2
    crop = ImageOps.expand(Image.fromarray(g), m, fill=255)
    words = [w for l in _read_lines(crop, codes, 7, (left - m, top - m)) for w in l["words"]]
    if not words:                                               # "single line" found nothing: try "block"
        found = _read_lines(crop, codes, 6, (left - m, top - m))
        words = max(found, key=lambda l: len(l["words"]))["words"] if found else []
    if words and depth < 2:                                     # Tesseract sometimes stops part-way along
        end = max(0, words[-1][2] + words[-1][4] - left)        # first blank column after the last word
        blank = (g < 140).sum(axis=0) == 0
        while end < g.shape[1] and not blank[end]:
            end += 1
        rest = g[:, end:] if end < g.shape[1] else g[:, :0]
        if rest.shape[1] > 2 * typical and (rest < 140).sum() > typical * typical:
            words += _read_piece(rest, codes, left + end, top, typical, depth + 1)
    if words or depth >= 2 or g.shape[1] < 8 * typical:
        return words
    blank = (g < 140).sum(axis=0) == 0
    mid, best = g.shape[1] // 2, None
    for x in range(g.shape[1] // 4, 3 * g.shape[1] // 4):    # blank column closest to the middle
        if blank[x] and (best is None or abs(x - mid) < abs(best - mid)):
            best = x
    if best is None:
        return words
    return (_read_piece(g[:, :best], codes, left, top, typical, depth + 1) +
            _read_piece(g[:, best:], codes, left + best, top, typical, depth + 1))


def _uncovered_lines(img, lines, codes, typical, is_text):
    """Last safety net: ink on the page that no Tesseract pass turned into words (common for text
    inside boxes, which some Tesseract versions skip). Box borders are removed, the leftover ink is
    cut into text lines, and each one is read on its own."""
    import numpy as np
    if not typical:
        return []
    gray = np.array(img.convert("L"))
    ink = gray < 140
    H, W = ink.shape
    pad = max(2, typical // 6)
    for l in lines:                                             # what was already read
        for _, _, x, y, w, h in l["words"]:
            ink[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad] = False
    ink &= ~_runs(ink, max(20, W // 12), 1)                     # horizontal rules and box edges
    ink &= ~_runs(ink, max(20, int(2.5 * typical)), 0)          # vertical edges, scan borders
    rows = ink.sum(axis=1) > max(3, typical // 4)
    found, y = [], 0
    while y < H:                                                # bands of rows holding ink
        if not rows[y]:
            y += 1
            continue
        y0 = y
        while y < H and (rows[y] or rows[y:y + typical // 3].any()):
            y += 1
        if 0.5 * typical <= y - y0 <= 3 * typical:
            top, bottom = max(0, y0 - typical // 2), min(H, y + typical // 2)   # keep vowel signs above/below
            band = ink[top:bottom]
            cols = band.sum(axis=0) > 0
            x = 0
            while x < W:                                        # pieces of the line split by wide gaps
                if not cols[x]:
                    x += 1
                    continue
                x0 = x
                while x < W and cols[x:x + 2 * typical].any():
                    x += 1
                piece = band[:, x0:x]
                if piece.sum() > typical * typical and x - x0 > 2 * typical:   # words, not specks
                    left = max(0, x0 - typical // 2)
                    # the page itself, with box edges and already-read words painted white
                    g = gray[top:bottom, left:x + typical // 2].copy()
                    g[(g < 140) & ~band[:, left:x + typical // 2]] = 255
                    words = _read_piece(g, codes, left, top, typical)
                    if words and is_text(" ".join(w[0] for w in words)):
                        found.append({"key": (7, top, left, 0, 0), "top": min(w[3] for w in words),
                                      "bottom": max(w[3] + w[5] for w in words),
                                      "right": max(w[2] + w[4] for w in words), "words": words, "inserted": True})
    return found


def _clean_line(img, line, allowed, indic_codes, typical):
    """Fix the words Tesseract read as English junk on an Indian-language page."""
    out = []
    for word, conf, x, y, w, h in line["words"]:
        latin = LATIN_WORD.search(word)
        if WEB.search(word) or (latin and conf >= 75 and len(regex.findall(r"[A-Za-z]", word)) >= 4):
            out.append(word)                           # web address, or a confident English word
            continue
        suspect = not regex.search(rf"[{allowed}]", word) and (
            (latin and (conf < TRUSTED_LATIN or len(word) <= 2)) or not regex.search(r"[\p{L}\d]", word))
        first = not out
        if first and len(line["words"]) > 1 and regex.fullmatch(r"[^\p{L}\p{N}(\[\"'‘“]", word):
            word = "•"                                 # a bullet read as a symbol ("@", "®", "e")
        elif first and h < 0.75 * typical and len(regex.findall(r"\X", word)) == 1 and not regex.match(r"\p{L}", word):
            word = "•"                                 # a bullet read as a digit or symbol ("०", "o", ">")
        elif suspect and first and h < 0.75 * typical:
            word = "•"                                 # small mark at the start of a line: a bullet
        elif suspect:
            pad = max(4, h // 4)
            crop = img.crop((max(0, x - pad), max(0, y - pad), x + w + pad, y + h + pad))
            again = pytesseract.image_to_string(crop, lang=indic_codes, config="--psm 8").strip()
            chars = [c for c in again if not c.isspace()]
            good = sum(1 for c in chars if regex.match(rf"[{allowed}]", c))
            if chars and good >= 0.6 * len(chars) and not LATIN_WORD.search(again):
                word = again
            elif regex.fullmatch(r"[(\[{\"'“‘]?[-–:;,.!?।()\]}\"'”’%/]*", word) and not latin:
                pass                                   # plain punctuation: keep
            elif len(regex.findall(r"[A-Za-z]", word)) >= 3:
                pass                                   # likely real English ("(DBT)"): keep, review will see it
            else:
                word = "•" if first else ""            # a bullet mark starts a line; anything else is junk
        if word:
            out.append(word)
    return " ".join(out)


def render(page, dpi):
    """The page as an RGB picture at `dpi` dots per inch."""
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def ocr_page(page, langs, dpi):
    return ocr_image(render(page, dpi), langs)


BOX_MARK = regex.compile(r"[|\[\]{}_]+")          # leftover bits of a box or table line read as a "word"


def ocr_image(img, langs):
    """OCR one page.
    - Two Tesseract passes: automatic page layout, then "one block of text"; lines only the second
      pass found (boxed titles, framed notes) are added where they sit on the page. Ink that neither
      pass read is then cut into lines and read line by line (box borders removed first).
    - Indic pages are read with the language(s) + English, so English words come out right; words
      Tesseract wrongly read as English ("PAAR", "Vv", ">") are read again in the Indic language
      only, and dropped if they still are not text (a bullet becomes "•"). Web addresses are kept.
    - A new paragraph starts after a wide vertical gap (a title above text), or where Tesseract starts
      one and the previous line ends a sentence.
    - Before reading: a page whose text runs sideways is turned upright, and checkboxes and table
      lines are painted out (they come out as "[ |" junk and make Tesseract skip whole lines).
    Returns the paragraphs as {"text", "bbox"} like page_blocks."""
    codes = tesseract_codes(langs)
    indic = [l for l in langs if LANGUAGES[l][1] != "Latin"]
    img = clear_form_marks(upright(img))
    lines = _read_lines(img, codes, 3)
    for extra in _missing_lines(lines, _read_lines(img, codes, 6)):
        pos = next((i for i, l in enumerate(lines) if l["top"] > extra["top"]), len(lines))
        lines.insert(pos, extra)
    heights = sorted(w[5] for l in lines for w in l["words"])
    typical = heights[len(heights) // 2] if heights else 0
    if indic:
        indic_codes = "+".join(dict.fromkeys(LANGUAGES[l][0] for l in indic))
        allowed = "".join(rf"\p{{Script={LANGUAGES[l][1]}}}" for l in indic)
        is_text = lambda t: len(regex.findall(rf"[{allowed}]", t)) >= 4
    else:
        is_text = lambda t: len(regex.findall(r"[A-Za-z]{3,}", t)) >= 2
    for extra in _uncovered_lines(img, lines, codes, typical, is_text):
        pos = next((i for i, l in enumerate(lines) if l["top"] > extra["top"]), len(lines))
        lines.insert(pos, extra)
    # letter soup read out of photos and drawings: most words of the line have a low confidence
    # (lines only the extra passes found must be surer: on photos those passes read texture as letters)
    lines = [l for l in lines if sorted(w[1] for w in l["words"])[len(l["words"]) // 2]
             >= (MIN_INSERTED_CONF if l.get("inserted") else MIN_LINE_CONF)]
    right_margin = sorted(l["right"] for l in lines)[int(0.9 * (len(lines) - 1))] if lines else 0
    blocks, prev = [], None
    for l in lines:
        text = _clean_line(img, l, allowed, indic_codes, typical) if indic else \
            " ".join(w[0] for w in l["words"] if not BOX_MARK.fullmatch(w[0]))
        if not text:
            continue
        # Tesseract's paragraphs are trusted when the previous line ends a sentence or stops short of
        # the right margin (the last line of a paragraph or list item), not in mid-sentence
        new_par = bool(prev) and l["key"][:4] != prev["key"][:4] and (
            regex.search(r"[.?!।॥:;]\W*$", blocks[-1]["lines"][-1]) or prev["right"] < right_margin - 2 * typical)
        box = [min(w[2] for w in l["words"]), l["top"], l["right"], l["bottom"]]
        if not prev or new_par or l.get("inserted") or prev.get("inserted") or l["top"] - prev["bottom"] > typical:
            blocks.append({"lines": [], "bbox": box})        # new paragraph
        b = blocks[-1]
        b["lines"].append(text)
        b["bbox"] = [min(b["bbox"][0], box[0]), min(b["bbox"][1], box[1]), max(b["bbox"][2], box[2]),
                     max(b["bbox"][3], box[3])]
        prev = l
    return [{"text": "\n".join(b["lines"]), "bbox": _norm(b["bbox"], img.width, img.height)} for b in blocks]


# invisible control characters some PDFs carry (Excel refuses them); newlines and tabs are kept
CONTROL = regex.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def tidy(text):
    """Remove control characters, squeeze spaces, keep at most one blank line in a row."""
    out = []
    text = CONTROL.sub(" ", text)
    for line in text.splitlines():
        line = " ".join(line.split())
        if regex.fullmatch(r"[•>»➢\-–*·\s]+", line):   # a bullet mark alone on a line
            continue
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def extract(pdf, langs, pages=None, ocr="auto", dpi=300, can_ocr=True, progress=None):
    """Read a PDF (a path or the file's bytes).

    langs   list of names from LANGUAGES, e.g. ["Odia", "English"]
    pages   e.g. "1-5,8"; None = all
    ocr     "auto" (only scanned/garbled pages), "always" or "never"
    progress  optional function(done, total)
    Returns a list of {"page", "method", "text", "blocks"}; method is text, old font, OCR or empty;
    blocks are the page's text boxes / paragraphs, {"text", "bbox"}, bbox as page fractions.
    """
    doc = fitz.open(stream=pdf, filetype="pdf") if isinstance(pdf, (bytes, bytearray)) else fitz.open(pdf)
    scripts = list(dict.fromkeys(["Latin"] + [LANGUAGES[l][1] for l in langs]))
    fonts = font_map(doc, scripts) if ocr != "always" else {}
    todo = parse_pages(pages, doc.page_count)
    results = {}
    need_ocr = []
    for i in todo:                      # text layer first: quick
        page = doc[i]
        blocks, method = [], ""
        if ocr != "always":
            blocks = page_blocks(page, fonts)
            uses_font = fonts and any(s["font"] in fonts for b in page.get_text("dict")["blocks"]
                                      for l in b.get("lines", []) for s in l["spans"])
            method = "old font" if uses_font else "text"
        if ocr == "always" or (ocr == "auto" and not looks_readable("\n\n".join(b["text"] for b in blocks), scripts)):
            if can_ocr:
                need_ocr.append(i)
                continue
            method = "needs OCR (Tesseract missing)"
        results[i] = (blocks, method)
    done = len(results)
    if progress and done:
        progress(done, len(todo))
    if need_ocr:
        # OCR pages in parallel: each Tesseract run is its own process, so several pages are read at
        # once (one Tesseract thread each). PyMuPDF is not thread-safe, so pages are drawn one at a time.
        lock = threading.Lock()
        workers = max(1, min(OCR_WORKERS, len(need_ocr)))
        if workers > 1:
            os.environ["OMP_THREAD_LIMIT"] = "1"

        def job(i):
            with lock:
                img = render(doc[i], dpi)
            return ocr_image(img, langs)
        with ThreadPoolExecutor(workers) as pool:
            futures = {pool.submit(job, i): i for i in need_ocr}
            for f in as_completed(futures):     # progress is reported from this (the main) thread
                results[futures[f]] = (f.result(), "OCR")
                done += 1
                if progress:
                    progress(done, len(todo))
    out = []
    for i in todo:
        blocks, method = results[i]
        blocks = [{"text": tidy(b["text"]), "bbox": b["bbox"]} for b in blocks]
        blocks = [b for b in blocks if b["text"]]
        text = "\n\n".join(b["text"] for b in blocks)
        if not text and method != "needs OCR (Tesseract missing)":
            method = "empty"
        out.append({"page": i + 1, "method": method, "text": text, "blocks": blocks})
    return out


def to_txt(results):
    return "\n\n".join(f"===== Page {r['page']} =====\n{r['text']}" for r in results) + "\n"
