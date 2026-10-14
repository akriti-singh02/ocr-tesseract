"""Step 8: detect garbled text and normalise Unicode."""
import unicodedata
import regex  # the `regex` package understands \p{Script=...}; the built-in `re` does not

try:
    import ftfy                                  # repairs mojibake such as "à¤­à¤¾"
except ImportError:
    ftfy = None
try:
    from indicnlp.normalize.indic_normalize import IndicNormalizerFactory
    _indic = IndicNormalizerFactory()
except ImportError:
    _indic = None

# Virama (halant) of each Brahmi-derived script. A virama followed directly by another mark
# (vowel sign, another virama) is not valid text. Broken fonts produce exactly that:
# "प्ोटीन" (should be "प्रोटीन") is प + ् + ो, the "र" was lost.
VIRAMAS = "्্੍્୍்్್്"
BAD_PATTERNS = regex.compile(
    rf"[{VIRAMAS}][\p{{M}}]"            # virama + vowel sign  (dropped conjunct letter)
    r"|(?:^|\s)[\p{Mn}\p{Mc}]"          # word starts with a vowel sign or virama
    r"|[\p{Mc}][\p{Mc}]"                # two spacing vowel signs in a row
    r"|�|[-]"          # replacement character, private-use glyphs
    r"|Ã.|à¤|à¬"                       # UTF-8 read as Latin-1 (mojibake)
)

def script_ratio(text, script):
    """Share of letters that belong to `script` (e.g. 'Devanagari'). Low = wrong encoding/language."""
    letters = regex.findall(r"\p{L}", text)
    if not letters:
        return 0.0
    inside = regex.findall(rf"\p{{Script={script}}}", "".join(letters))
    return len(inside) / len(letters)

def garble_score(text, script="Latin"):
    """Bad character sequences per word. Clean text is ~0; > 0.02 usually means a broken layer."""
    words = text.split()
    if not words:
        return 0.0
    bad = len(BAD_PATTERNS.findall(text))
    if script != "Latin":
        # Latin-1 Supplement / Latin Extended letters inside Indic text = legacy or broken font glyphs
        bad += len(regex.findall(r"[À-ɏɐ-˿]", text))
    return bad / len(words)

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
QUOTES = {"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'", "–": "-", "—": "-", "−": "-"}
INVISIBLE = "​­﻿⁠"          # zero-width space, soft hyphen, BOM, word joiner

def normalise(text, lang_iso="en", plain_quotes=True):
    """Same cleaning for every file: fix mojibake, NFC, ligatures, invisible chars, spaces."""
    if ftfy:
        text = ftfy.fix_text(text, normalization="NFC")
    text = unicodedata.normalize("NFC", text)    # NFC, never NFKC, for Indic scripts
    for a, b in LIGATURES.items():
        text = text.replace(a, b)
    if plain_quotes:
        for a, b in QUOTES.items():
            text = text.replace(a, b)
    text = "".join(c for c in text if c not in INVISIBLE)   # ZWJ/ZWNJ (200D/200C) are kept
    if _indic and lang_iso in ("hi", "mr", "sa", "ne", "bn", "as", "or", "gu", "pa", "ta", "te", "kn", "ml"):
        try:
            text = _indic.get_normalizer(lang_iso).normalize(text)
        except Exception:
            pass
    text = regex.sub(r"[ \t ]+", " ", text)
    text = regex.sub(r" *\n *", "\n", text)
    return text.strip()

def numbers(text):
    """All numbers in a string, with Indic digits mapped to ASCII, so both sides can be compared."""
    table = {}
    for zero in (0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66, 0x0BE6, 0x0C66, 0x0CE6, 0x0D66):
        for d in range(10):
            table[zero + d] = str(d)
    return regex.findall(r"\d+(?:[.,]\d+)?", text.translate(table).replace(",", ""))

if __name__ == "__main__":
    for s in ["प्रोटीन 25 किग्रा", "प्ोटीन 25 किग्ा", "इसकɃ वृɺ", "Ghanjeevamrit is ﬁne", "à¤­à¤¾à¤°à¤¤"]:
        print(f"{s!r:30} garble={garble_score(s, 'Devanagari'):.2f} "
              f"deva={script_ratio(s, 'Devanagari'):.2f} -> {normalise(s, 'hi')!r}")
