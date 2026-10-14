"""Step 12: quality signals and review flags for every pair. Flag, don't delete."""
import hashlib
from collections import Counter
import regex
from clean import numbers, script_ratio, garble_score

def _pct(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, max(0, int(q * (len(v) - 1))))] if v else None

def review(rows, src_script="Latin", tgt_script="Devanagari", min_score=0.4, min_conf=60):
    """rows: dicts with src_text, tgt_text, score, alignment, (optional) src_conf, tgt_conf.
    Adds length_ratio, needs_manual_review (Yes/No) and review_reason."""
    ratios = [len(r["tgt_text"]) / len(r["src_text"]) for r in rows if r["src_text"] and r["tgt_text"]]
    lo, hi = _pct(ratios, 0.05), _pct(ratios, 0.95)
    seen = Counter()
    for r in rows:
        s, t = r["src_text"], r["tgt_text"]
        reasons = []
        if not s or not t:
            reasons.append("no partner in the other language")
        else:
            ratio = len(t) / len(s)
            r["length_ratio"] = round(ratio, 2)
            if r.get("score") not in (None, "") and float(r["score"]) < min_score:
                reasons.append(f"low similarity (< {min_score})")
            if r.get("alignment") not in (None, "1-1"):
                reasons.append(f"{r['alignment']} merge")
            if len(ratios) >= 20 and not (lo <= ratio <= hi):
                reasons.append("unusual length ratio")
            if set(numbers(s)) != set(numbers(t)):
                reasons.append("numbers differ")
            if not regex.search(r"\p{L}", s) or not regex.search(r"\p{L}", t):
                reasons.append("no words (numbers or symbols only)")
            elif s.strip().lower() == t.strip().lower():
                reasons.append("source and target identical (untranslated?)")
            if script_ratio(s, src_script) < 0.5 and regex.search(r"\p{L}{3}", s):
                reasons.append(f"source not in {src_script} script")
            if script_ratio(t, tgt_script) < 0.5 and regex.search(r"\p{L}{3}", t):
                reasons.append(f"target not in {tgt_script} script")
            if garble_score(s, src_script) > 0.05 or garble_score(t, tgt_script) > 0.05:
                reasons.append("garbled characters")
            for side in ("src_conf", "tgt_conf"):
                if r.get(side) not in (None, "") and float(r[side]) < min_conf:
                    reasons.append(f"low OCR confidence ({side[:3]})")
            key = hashlib.md5((s.lower() + "\t" + t.lower()).encode()).hexdigest()
            seen[key] += 1
            if seen[key] > 1:
                reasons.append("duplicate pair")
        r.setdefault("length_ratio", "")
        r["needs_manual_review"] = "Yes" if reasons else "No"
        r["review_reason"] = "; ".join(reasons)
    return rows
