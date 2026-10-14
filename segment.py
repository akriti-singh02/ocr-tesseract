"""Step 9: split block text into sentences, script-aware, without breaking on abbreviations."""
import regex

# Abbreviations that never end a sentence ...
NEVER_END = {"dr", "mr", "mrs", "ms", "prof", "fig", "figs", "no", "nos", "vs", "viz", "cf", "st", "jr", "sr",
             "vol", "ed", "eds", "e.g", "i.e", "approx", "ca", "al", "sp", "spp", "var", "cv", "dept", "govt"}
# ... and ones that often do ("... 25 kg. Then ..."): these end a sentence only before a capital letter.
MAYBE_END = {"etc", "kg", "ha", "cm", "mm", "km", "ml", "g", "l", "min", "max", "hrs", "ltd", "co", "inc"}
# Short Hindi/Indic abbreviations written with a full stop: से. (सेल्सियस), डॉ., कि.ग्रा., सं., पृ., ई.
INDIC_ABBREV = {"से", "डॉ", "कि", "ग्रा", "मि", "ली", "सं", "पृ", "ई", "पू", "प्रो", "प्र", "नं", "रु", "श्री", "डा"}
# Sentence-final marks: Latin . ? !   Devanagari/Odia/Bengali danda । and double danda ॥
END = r"[.?!।॥]"

# Languages that end sentences with a danda (।). In them a full stop is nearly always an abbreviation
# (ମି.ଲି. = ml, ई. पू. = BC, ড. = Dr), so "." ends a sentence only after a real word.
DANDA_LANGS = {"hi", "or", "bn", "as", "pa", "sa", "ne", "mai", "doi", "mni"}

def split_sentences(text, lang_iso="en"):
    """Cut after an end mark followed by a space (or the end of the text), except after
    abbreviations, initials like 'R.' or '(L.)', and decimals ('2.5' has no space, never splits)."""
    text = " ".join(text.split())
    danda = lang_iso in DANDA_LANGS
    out, start = [], 0
    for m in regex.finditer(rf"{END}+[\"'”’)\]]*(?=\s|$)", text):
        end = m.end()
        before = text[start:m.start()].split()
        last = before[-1] if before else ""
        if m.group().startswith(".") and end < len(text):
            word = last.lower().lstrip("(").rstrip(".")
            nxt = text[end:].lstrip()[:1]
            if word in NEVER_END or last.lstrip("(").rstrip(".").split(".")[-1] in INDIC_ABBREV:
                continue
            if danda and not regex.match(r"\p{Lu}", nxt):
                core = last.rstrip(".").split(".")[-1]
                # abbreviation: short (<= 3 letters), dotted inside (ଇ.ସି.), or glued to a number (୨୦୦ଲି.)
                if len(regex.findall(r"\X", core)) <= 3 or "." in last.rstrip(".") or regex.search(r"\d", last):
                    continue
            if regex.fullmatch(r"\(?\p{Lu}", last):        # an initial: "R." "(L."
                continue
            if (word in MAYBE_END or nxt.islower()) and not nxt.isupper():
                continue
        out.append(text[start:end].strip())
        start = end
    if text[start:].strip():
        out.append(text[start:].strip())
    return [s for s in out if regex.search(r"\p{L}|\d", s)]

def split_items(text):
    """Lists: bullets, numbered items, '#' separators and line breaks become separate units."""
    parts = regex.split(r"\s*(?:\n|#|•|▪|●|◦|(?<=^|\s)[-*]\s|(?<=^|\s)\(?\d{1,2}[.)]\s)\s*", text)
    return [p.strip() for p in parts if p and p.strip()]

if __name__ == "__main__":
    print(split_sentences("Pennisetum glaucum (L.) R. Br. is grown e.g. in Rajasthan. Yield is 2.5 t/ha. Sow approx. 4 kg/ha!"))
    print(split_sentences("इष्टतम तापमान 20° से. से 28° से. होता है। इष्टतम वर्षा 35 - 50 सेमी होती है। क्या यह सही है?", "hi"))
    print(split_sentences("ଓଡ଼ିଶା ଭାରତର ଏକ ସୁନ୍ଦର ରାଜ୍ୟ। ଭୁବନେଶ୍ୱର ଏହାର ରାଜଧାନୀ।", "or"))
