"""Convert Hindi typed in legacy (non-Unicode) fonts to Unicode Devanagari.

NIOS Hindi-medium PDFs are set in Walkman-Chanakya, a Kruti Dev-style font: the PDF text
layer holds Latin letters ("lkekftd foKku") that only look like Hindi on screen
("सामाजिक विज्ञान"). This module maps them back. The map follows the usual Kruti Dev 010
tables, with the Walkman-Chanakya differences seen in the NIOS PDFs:
"/" = ध (Kruti: ध्), "è" = ध्, "¼" = द्ध, "( )" are real brackets, "_" = ";", "]" = ",",
"iQ" = फ, digits print as Devanagari digits.

    from legacy_hindi import chanakya_to_unicode, is_legacy_font
    chanakya_to_unicode("lkekftd foKku dh izLrkouk")   # 'सामाजिक विज्ञान की प्रस्तावना'
"""

import re

LEGACY_FONT = re.compile(r"chanakya|kruti|krutidev|devlys|walkman", re.I)


def is_legacy_font(fontname):
    return bool(LEGACY_FONT.search(fontname or ""))


# Order matters: longer sequences first, consonant+"k" (full form) before the bare "k" matra.
_PAIRS = [
    ("ñ", "॰"), ("Q+Z", "QZ+"), ("sas", "sa"), ("aa", "a"), ("ZZ", "Z"),
    ("0", "०"), ("1", "१"), ("2", "२"), ("3", "३"), ("4", "४"),
    ("5", "५"), ("6", "६"), ("7", "७"), ("8", "८"), ("9", "९"),
    # nukta letters
    ("¶+", "फ़्"), ("d+", "क़"), ("[+k", "ख़"), ("[+", "ख़्"), ("x+", "ग़"), ("T+", "ज़्"),
    ("t+", "ज़"), ("M+", "ड़"), ("<+", "ढ़"), ("Q+", "फ़"), (";+", "य़"), ("j+", "ऱ"), ("u+", "ऩ"),
    # conjunct glyphs
    ("Ùk", "त्त"), ("Ù", "त्त्"), ("ä", "क्त"), ("–", "दृ"), ("—", "कृ"), ("Ñ", "कृ"),
    ("é", "न्न"), ("™", "न्न्"), ("à", "ह्न"), ("á", "ह्य"), ("â", "हृ"), ("ã", "ह्म"),
    ("ºz", "ह्र"), ("º", "ह्"), ("í", "द्द"), ("¼", "द्ध"), ("{k", "क्ष"), ("{", "क्ष्"),
    ("=k", "त्र"), ("«", "त्र्"), ("=", "त्र्"), ("Nî", "छ्य"), ("Vî", "ट्य"), ("Bî", "ठ्य"),
    ("Mî", "ड्य"), ("<î", "ढ्य"), ("|", "द्य"), ("K", "ज्ञ"), ("}", "द्व"), ("J", "श्र"),
    ("Vª", "ट्र"), ("Mª", "ड्र"), ("<ª", "ढ्र"), ("Nª", "छ्र"), ("ª", "्र"), ("Ø", "क्र"),
    ("Ý", "फ्र"), ("nzZ", "र्द्र"), ("æ", "द्र"), ("ç", "प्र"), ("Á", "प्र"), ("xz", "ग्र"),
    ("#", "रु"), (":", "रू"), ("iQ", "फ"),
    # independent vowels
    ("v‚", "ऑ"), ("vks", "ओ"), ("vkS", "औ"), ("vk", "आ"), ("v", "अ"), ("b±", "ईं"),
    ("Ã", "ई"), ("bZ", "ई"), ("b", "इ"), ("m", "उ"), ("Å", "ऊ"), (",s", "ऐ"), (",", "ए"),
    # consonants (capital / bare = half form, +k = full form)
    ("ô", "क्क"), ("d", "क"), ("Dk", "क"), ("D", "क्"), ("[k", "ख"), ("[", "ख्"),
    ("x", "ग"), ("Xk", "ग"), ("X", "ग्"), ("Ä", "घ"), ("?k", "घ"), ("?", "घ्"), ("³", "ङ"),
    ("p", "च"), ("Pk", "च"), ("P", "च्"), ("N", "छ"), ("t", "ज"), ("Tk", "ज"), ("T", "ज्"),
    (">", "झ"), ("÷", "झ्"), ("¥", "ञ"), ("ê", "ट्ट"), ("ë", "ट्ठ"), ("V", "ट"), ("B", "ठ"),
    ("ì", "ड्ड"), ("ï", "ड्ढ"), ("M", "ड"), ("<", "ढ"), (".k", "ण"), (".", "ण्"),
    ("r", "त"), ("Rk", "त"), ("R", "त्"), ("Fk", "थ"), ("F", "थ्"), ("n", "द"),
    ("/", "ध"), ("è", "ध्"), ("u", "न"), ("Uk", "न"), ("U", "न्"), ("i", "प"), ("Ik", "प"),
    ("I", "प्"), ("Q", "फ"), ("¶", "फ्"), ("c", "ब"), ("Ck", "ब"), ("C", "ब्"), ("Hk", "भ"),
    ("H", "भ्"), ("e", "म"), ("Ek", "म"), ("E", "म्"), (";", "य"), ("¸", "य्"), ("j", "र"),
    ("y", "ल"), ("Yk", "ल"), ("Y", "ल्"), ("G", "ळ"), ("o", "व"), ("Ok", "व"), ("O", "व्"),
    ("'k", "श"), ("'", "श्"), ('"k', "ष"), ('"', "ष्"), ("l", "स"), ("Lk", "स"), ("L", "स्"),
    ("g", "ह"),
    # vowel signs and marks
    ("‚", "ॉ"), ("ks", "ो"), ("kS", "ौ"), ("k", "ा"), ("h", "ी"), ("q", "ु"), ("w", "ू"),
    ("`", "ृ"), ("s", "े"), ("S", "ै"), ("a", "ं"), ("¡", "ँ"), ("~", "्"), ("+", "़"),
    ("z", "्र"),
    # punctuation
    ("A", "।"), ("-", "."), ("&", "-"), ("]", ","), ("_", ";"), ("@", "/"),
    ("^", "‘"), ("*", "’"), ("Þ", "“"), ("ß", "”"), ("¿", "{"), ("À", "}"),
]

_CONS = "[क-हक़-य़]़?"
_CLUSTER = f"(?:{_CONS}्)*{_CONS}"
_MATRAS = "[ा-ौँ-ःॢॣ]*"
_I_MATRA = re.compile(f"ि({_CLUSTER})")          # "f" is typed before the consonant
_REPH = re.compile(f"({_CLUSTER})({_MATRAS})Z")        # "Z" (र्) is typed after it


def chanakya_to_unicode(text):
    if not text:
        return text
    # visarga vs colon: "nq%[k" = दुःख, but "bfrgkl% " = "इतिहास: "
    text = re.sub(r"%(?=[A-Za-z'\"\[{/;])", "\x00", text).replace("%", "\x01")
    for a, b in _PAIRS:
        text = text.replace(a, b)
    text = text.replace("\x00", "ः").replace("\x01", ":").replace("f", "\u093f")
    text = _I_MATRA.sub(r"\1" + "\u093f", text)
    text = _REPH.sub("र्" + r"\1\2", text)
    text = text.replace("्ा", "")               # half form + ा = full letter
    text = text.replace("Z", "र्")                         # stray reph with nothing before it
    # typing-order slips the font hides: "vkas" (आ ं े) = ओं, "isz" (प े ्र) = प्रे
    text = re.sub("([\u0901\u0902])([\u0947\u0948\u094b\u094c])", r"\2\1", text)
    text = re.sub("([\u0947\u0948])\u094d\u0930", "\u094d\u0930" + r"\1", text)
    text = text.replace("द्े", "द्दे")                      # "mn~s';" is printed as उद्देश्य
    text = text.replace("अा", "आ").replace("आे", "ओ").replace("आै", "औ")
    text = text.replace("ाे", "ो").replace("ाै", "ौ")
    return text


def convert_spans(spans):
    """Join PyMuPDF spans into one string, converting runs set in a legacy Hindi font.
    Wingdings characters (the bullets in NIOS PDFs) become "•"."""
    out, run = [], []

    def flush():
        if run:
            out.append(chanakya_to_unicode("".join(run)))
            run.clear()

    for s in spans:
        font = s.get("font", "")
        if is_legacy_font(font):
            run.append(s["text"])
            continue
        flush()
        out.append(re.sub(r"\S", "•", s["text"]) if "wingding" in font.lower() else s["text"])
    flush()
    return "".join(out)
