"""Convert Odia typed in a legacy (non-Unicode) font to Unicode Odia.

The ICAR-NRRI / KVK Cuttack Odia agro-advisory PDFs are set in a Sarala-style Odia font: the
PDF text layer holds Latin letters and symbols ("Kéhò aòmû^ ùK¦â") that only look like Odia
on screen ("କୃଷି ବିଜ୍ଞାନ କେନ୍ଦ୍ର"). The map below was worked out by comparing the text layer
with the printed pages of the 06.10.2026 Cuttack bulletin.

Rules on top of the character map:
  - "ù" (େ) is typed before its consonant cluster: moved after it; "ùû" = ୋ, "ùø" = ୌ, "ù÷" = ୈ
  - "ð" (reph, ର୍) is typed after its cluster and vowel signs: moved before the cluster
  - ASCII digits print as Odia digits

    from legacy_odia import sarala_to_unicode
    sarala_to_unicode("Kéhò aòmû^ ùK¦â KUK")   # 'କୃଷି ବିଜ୍ଞାନ କେନ୍ଦ୍ର କଟକ'
"""

import re
import unicodedata

_MAP = {
    # independent vowels
    "@": "ଅ", "A": "ଇ", "C": "ଉ", "G": "ଏ", "I": "ଓ",
    # consonants
    "K": "କ", "L": "ଖ", "M": "ଗ", "N": "ଘ", "P": "ଚ", "Q": "ଛ", "R": "ଜ", "S": "ଝ",
    "U": "ଟ", "V": "ଠ", "W": "ଡ", "X": "ଢ଼", "Y": "ଣ", "Z": "ତ", "[": "ଥ", "\\": "ଦ",
    "]": "ଧ", "^": "ନ", "_": "ପ", "`": "ଫ", "a": "ବ", "b": "ଭ", "c": "ମ", "~": "ଯ",
    "d": "ୟ", "e": "ର", "f": "ଲ", "k": "ଳ", "g": "ଶ", "h": "ଷ", "i": "ସ", "j": "ହ",
    # conjunct glyphs
    "l": "କ୍ଷ", "m": "ଜ୍ଞ", "«": "ନ୍ତ", "¦": "ନ୍ଦ", "§": "ନ୍ଧ", "‚": "ଞ୍ଚ", "Š": "ଣ୍ଡ",
    "´": "ମ୍ବ", "¸": "ମ୍ଭ", "¯": "ପ୍ତ", "Ã": "ଷ୍କ", "u": "ଙ୍କ", "w": "ଙ୍ଗ", "y": "ଚ୍ଚ",
    "Ê": "ସ୍ୱ", "É": "ସ୍ତ", "Æ": "ସ୍ପ", "ª": "ନ୍ତ୍ର", "¬": "ନ୍ଜ", "Á": "ଳ୍ପ", "¡": "ଦ୍ଧ",
    "½": "ଶ୍ଚ", "z": "ଚ୍ଛ",
    # more glyphs of the Akruti Odia fonts (SRI paddy booklet, Odia edition)
    "¤": "ଧ୍ୟ", "q": "କ୍ତ", "‰": "ଣ୍ଣ", "µ": "ମ୍ପ", "Ì": "ଳ୍ପ", "²": "ବ୍ଧ", "Ÿ": "ଦ୍ଦ",
    "¹": "ମ୍ମ", "Ä": "ସ୍କ",
    # subscript (post-base) forms
    "â": "୍ର", "ä": "୍ଲ", "ý": "୍ୟ", "Ú": "୍ଥ", "Ü": "୍ନ", "Ö": "୍ଟ", "è": "୍ସ", "ß": "୍ୱ",
    "à": "୍ମ", "Ñ": "୍କ", "×": "୍ଠ",
    # vowel signs and marks
    "û": "ା", "ò": "ି", "ô": "ି", "ÿ": "଼", "ó": "ିଁ", "ú": "ୀ", "ê": "ୁ", "ë": "ୁ", "ì": "ୂ", "é": "ୃ",
    "ù": "େ", "ø": "ୗ", "÷": "ୖ", "ñ": "ଁ", "õ": "ଂ", "ü": "ଃ", "þ": "୍",
    # punctuation
    "ö": "।", "": "•",
    "0": "୦", "1": "୧", "2": "୨", "3": "୩", "4": "୪", "5": "୫", "6": "୬", "7": "୭",
    "8": "୮", "9": "୯",
}

_CONS = "[କ-ହଡ଼-ୟୱ]଼?"
_CLUSTER = f"{_CONS}(?:୍{_CONS})*"
_SIGNS = "[ା-ୌୖୗଁ-ଃ]*"
_PRE_E = re.compile(f"େ({_CLUSTER})")
_SUB_AFTER_SIGN = re.compile(f"([\u0b3e-\u0b4c\u0b56\u0b57]+)(\u0b4d{_CONS})")
_REPH = re.compile(f"({_CLUSTER})({_SIGNS})\x00")


def akruti_to_unicode(text, digits=True):
    """Akruti Odia fonts (AkrutiOriSarala-99 ...): same layout, but "Á" is ଷ୍ଟ (ପୋଷ୍ଟ, କମ୍ପୋଷ୍ଟ).
    The ତ୍ତ glyph has no character code in these PDFs: it comes out as an invisible control
    character, "�" or (Bhuban font) "•" inside a word. The same happens to ଞ୍ଚ, whose only common
    word is ଅଞ୍ଚଳ, so that word is put right afterwards."""
    text = re.sub(r"(?<=\S)•", "\x1f", text).replace("\ufffd", "\x1f")
    out = sarala_to_unicode(text, digits, {"Á": "ଷ୍ଟ", "\x1f": "ତ୍ତ"})
    return out.replace("ଅତ୍ତଳ", "ଅଞ୍ଚଳ")


def sarala_to_unicode(text, digits=True, extra=None):
    if not text:
        return text
    table = {**_MAP, **extra} if extra else _MAP
    out = []
    for ch in text:
        if ch == "ð":
            out.append("\x00")
        elif ch.isdigit() and not digits:
            out.append(ch)
        else:
            out.append(table.get(ch, ch))
    t = "".join(out)
    t = _PRE_E.sub(r"\1" + "େ", t)          # େ typed first -> after its cluster
    t = _SUB_AFTER_SIGN.sub(r"\2\1", t)          # "ùWûâ": subscript typed after the vowel sign
    t = _REPH.sub("ର୍" + r"\1\2", t)             # reph typed last -> before its cluster
    t = re.sub(r"\s+\x00(?=\s|$)", "", t)          # stray reph glyph with no letter
    t = t.replace("\x00", "ର୍")
    t = unicodedata.normalize("NFC", t)           # େ+ା = ୋ, େ+ୗ = ୌ, େ+ୖ = ୈ
    return t.replace("ଅା", "ଆ")


def is_legacy_odia(text):
    """True for span text in the legacy font (many of its vowel-sign glyphs, few spaces of English)."""
    letters = [c for c in text if not c.isspace()]
    if len(letters) < 2:
        return False
    marks = sum(c in "ûòùêúéþñõâä" for c in letters)
    return marks / len(letters) > 0.08


def convert_spans(spans, legacy_fonts):
    """Join PyMuPDF spans, converting those whose font is in legacy_fonts."""
    out = []
    for s in spans:
        if s["font"] in legacy_fonts:
            out.append(sarala_to_unicode(s["text"]))
        elif s["text"] == "":
            out.append("•")
        else:
            out.append(s["text"])
    return "".join(out)


def legacy_fonts_of(doc):
    """Names of the fonts in doc whose text looks like legacy-encoded Odia."""
    from collections import defaultdict
    text = defaultdict(str)
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    if len(text[s["font"]]) < 20000:
                        text[s["font"]] += s["text"]
    return {f for f, t in text.items() if is_legacy_odia(t)}
