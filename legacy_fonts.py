"""Legacy (non-Unicode) Indic fonts: find them in a PDF and convert their text to Unicode.

Many Indian government PDFs are typed in fonts such as Kruti Dev, Walkman-Chanakya or DevLys
(Hindi) and Sarala / Akruti-style fonts (Odia). The text layer then holds Latin letters and
symbols ("lkekftd foKku") that only *look* like Indic script on screen. Copying that text gives
garbage, and OCR is slow and loses accuracy, so the best fix is a glyph map.

Converters available (add your own to CONVERTERS: any function str -> str):
  chanakya / krutidev  Hindi, Kruti Dev 010 tables + Walkman-Chanakya differences (legacy_hindi.py)
  sarala               Odia, Sarala-style font of the ICAR/KVK advisories (legacy_odia.py)

How a font is picked for conversion (font_map):
  --legacy auto      font name matches a known legacy family, OR (for an Indic language) the font's
                     text is Latin-looking, is not English, and becomes >= 80% target script once converted
  --legacy hin=chanakya ori=sarala   force a converter for that language's legacy fonts
  --legacy none      never convert
"""
import re
from collections import defaultdict
import regex
from legacy_hindi import chanakya_to_unicode
from legacy_odia import akruti_to_unicode, sarala_to_unicode

CONVERTERS = {"chanakya": chanakya_to_unicode, "krutidev": chanakya_to_unicode, "sarala": sarala_to_unicode,
              "akruti": akruti_to_unicode}
# font-name patterns that always mean "legacy font" -> converter
# (Odia first: "AkrutiOriSarala" contains "kruti" but is an Odia font, not Kruti Dev)
FONT_NAMES = [(re.compile(r"akruti.*ori", re.I), "akruti"),
              (re.compile(r"sarala|oriya.?ms|odia.?ms", re.I), "sarala"),
              (re.compile(r"chanakya|(?<!a)kruti|devlys|walkman", re.I), "chanakya")]
# default converter tried by the auto heuristic for each script
BY_SCRIPT = {"Devanagari": "chanakya", "Oriya": "sarala"}
DINGBATS = re.compile(r"wingding|webding|dingbat|symbol|zapf", re.I)
ENGLISH = set("the of and to in is for on with by as be are this that from or at an it was which can "
              "not have has will their its also these such been more other".split())


def english_share(text):
    words = re.findall(r"[a-z]+", text.lower())
    return sum(w in ENGLISH for w in words) / len(words) if words else 0.0


def script_share(text, script):
    letters = regex.findall(r"\p{L}", text)
    return len(regex.findall(rf"\p{{Script={script}}}", "".join(letters))) / len(letters) if letters else 0.0


def font_samples(doc, max_chars=20000):
    text = defaultdict(str)
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    if len(text[s["font"]]) < max_chars:
                        text[s["font"]] += s["text"] + " "
    return text


def font_map(doc, scripts, spec="auto"):
    """{font name: converter function} for the fonts in `doc` that hold legacy-encoded text.
    scripts: Unicode scripts of the languages expected in the document, e.g. ["Latin", "Devanagari"].
    spec: "auto", "none", or {"Devanagari": "chanakya", ...} (forced converter per script)."""
    if spec == "none":
        return {}
    forced = spec if isinstance(spec, dict) else {}
    out = {}
    for font, text in font_samples(doc).items():
        if DINGBATS.search(font) or script_share(text, "Latin") < 0.6:   # bullets, or already Unicode              # already real Indic Unicode (or no letters)
            continue
        name_hit = next((conv for pat, conv in FONT_NAMES if pat.search(font)), None)
        for script in scripts:
            if script == "Latin":
                continue
            conv = forced.get(script) or name_hit or BY_SCRIPT.get(script)
            if not conv:
                continue
            if name_hit and not forced:
                out[font] = CONVERTERS[name_hit]; break
            if english_share(text) > 0.08:                 # this font is simply English
                break
            if len(regex.findall(r"\p{L}", text)) >= 20 and \
                    script_share(CONVERTERS[conv](text), script) >= 0.8:
                out[font] = CONVERTERS[conv]; break
    return out


def convert_spans(spans, fonts):
    """Join the spans of one line; runs of spans in a legacy font are converted together
    (a pre-base vowel sign can sit in a different span from its consonant)."""
    out, run, conv = [], [], None

    def flush():
        if run:
            out.append(conv("".join(run)))
            run.clear()

    for s in spans:
        f = fonts.get(s["font"])
        if f is not None:
            if conv is not None and f is not conv:
                flush()
            conv = f
            run.append(s["text"])
            continue
        flush()
        text = s["text"]
        if DINGBATS.search(s["font"]):
            text = re.sub(r"\S", "•", text)                # dingbat bullets
        out.append(text)
    flush()
    return "".join(out)


def clip_text(page, rect, fonts):
    """Text inside a rectangle (e.g. a table cell), legacy runs converted."""
    lines = []
    for b in page.get_text("dict", clip=rect)["blocks"]:
        for l in b.get("lines", []):
            lines.append(convert_spans(l["spans"], fonts) if fonts else "".join(s["text"] for s in l["spans"]))
    return " ".join(" ".join(lines).split())


def page_text(page, fonts):
    """Whole-page text with legacy runs converted (used by triage)."""
    if not fonts:
        return page.get_text("text")
    return "\n".join(convert_spans(l["spans"], fonts)
                     for b in page.get_text("dict")["blocks"] for l in b.get("lines", []))
