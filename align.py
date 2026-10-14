"""Steps 10-11: sentence alignment.

Scorers turn a (source group, target group) of sentences into a similarity in [0, 1]:
  LaBSEScorer    multilingual sentence embeddings (best; needs sentence-transformers + model download)
  LexicalScorer  length + numbers + shared tokens + optional bilingual dictionary (offline, no model)
  Model1Scorer   IBM Model 1 word-translation probabilities learned from already-aligned pairs
align() is a monotonic dynamic-programming aligner that allows 1-1, 1-2, 2-1, 2-2, 1-3, 3-1, 1-0, 0-1.
"""
import math
from collections import defaultdict
import regex
from clean import numbers

def tokens(s):
    return [t.lower() for t in regex.findall(r"\p{L}[\p{L}\p{M}]*|\d+(?:[.,]\d+)?", s)]

class LaBSEScorer:
    """Cosine similarity of multilingual sentence embeddings from a sentence-transformers model:
    LaBSE by default, or e.g. BAAI/bge-m3. Each model is loaded once per run of the program."""
    loaded = {}
    rescue = 0.7      # score needed to pair two leftover sentences out of order (dataset._rescue)

    def __init__(self, model="sentence-transformers/LaBSE", device=None):
        if model not in self.loaded:
            from sentence_transformers import SentenceTransformer
            self.loaded[model] = SentenceTransformer(model, device=device)
        self.model = self.loaded[model]
        self.cache = {}
    def prepare(self, texts):
        """Embed every text the aligner may ask about in one batch (much faster than one by one)."""
        new = [t for t in set(texts) if t not in self.cache]
        if new:
            for t, e in zip(new, self.model.encode(new, batch_size=64, normalize_embeddings=True)):
                self.cache[t] = e
    def __call__(self, src, tgt):
        a, b = " ".join(src), " ".join(tgt)
        self.prepare([a, b])
        return max(0.0, float(self.cache[a] @ self.cache[b]))   # cosine (vectors are normalised)

class MeanScorer:
    """Average of several scorers (e.g. LaBSE and BGE-M3): steadier for languages neither model
    knows well, because their mistakes rarely coincide."""
    rescue = 0.7
    def __init__(self, scorers):
        self.scorers = scorers
    def prepare(self, texts):
        for s in self.scorers:
            if hasattr(s, "prepare"):
                s.prepare(texts)
    def __call__(self, src, tgt):
        return sum(s(src, tgt) for s in self.scorers) / len(self.scorers)

class LexicalScorer:
    """No neural model. Combines:
       length  - translations have predictable length ratios (Gale & Church idea)
       numbers - numbers usually survive translation unchanged
       anchors - names, units, Latin words that appear identically on both sides
       dict    - word pairs from an optional bilingual dictionary file (src<TAB>tgt per line)"""
    def __init__(self, ratio=1.0, dictionary=None):
        self.mu, self.sigma = math.log(ratio), 0.35
        self.dict = defaultdict(set)
        if dictionary:
            for line in open(dictionary, encoding="utf-8"):
                if "\t" in line:
                    s, t = line.rstrip("\n").split("\t")[:2]
                    self.dict[s.lower()].add(t.lower())
    def fit_ratio(self, src_texts, tgt_texts):
        """Character-length ratio of the whole document pair, e.g. Hindi ~1.1 x English."""
        a, b = sum(map(len, src_texts)), sum(map(len, tgt_texts))
        if a and b:
            self.mu = math.log(b / a)
    def __call__(self, src, tgt):
        a, b = " ".join(src), " ".join(tgt)
        length = math.exp(-((math.log((len(b) + 1) / (len(a) + 1)) - self.mu) ** 2) / (2 * self.sigma ** 2))
        na, nb = set(numbers(a)), set(numbers(b))
        num = len(na & nb) / len(na | nb) if (na or nb) else None
        ta, tb = set(tokens(a)), set(tokens(b))
        shared = {t for t in ta & tb if len(t) > 2 and not t.isdigit()}
        anchor = min(1.0, len(shared) / 2) if shared else None
        dic = None
        if self.dict:
            hits = sum(1 for t in ta if self.dict.get(t, set()) & tb)
            known = sum(1 for t in ta if t in self.dict)
            dic = hits / known if known else None
        parts = [(length, 1.0)] + [(v, w) for v, w in ((num, 1.0), (anchor, 0.5), (dic, 1.5)) if v is not None]
        return sum(v * w for v, w in parts) / sum(w for _, w in parts)

class Model1Scorer:
    """IBM Model 1, trained with EM on sentence pairs you trust (e.g. confident 1-1 pairs from a
    first LexicalScorer pass, or a glossary). Score = how well each side's words are explained
    by the other side's words, averaged in both directions, blended with the length score."""
    def __init__(self, pairs, iters=8, base=None):
        pairs = [(tokens(s), tokens(t)) for s, t in pairs]
        self.t_st = self._train(pairs, iters)                       # p(target word | source word)
        self.t_ts = self._train([(t, s) for s, t in pairs], iters)  # p(source word | target word)
        self.base = base or LexicalScorer()
    @staticmethod
    def _train(pairs, iters):
        t = defaultdict(lambda: 1e-3)
        for _ in range(iters):
            count, total = defaultdict(float), defaultdict(float)
            for src, tgt in pairs:
                src = src + ["<null>"]
                for w in set(tgt):
                    z = sum(t[(w, s)] for s in src)
                    for s in src:
                        c = t[(w, s)] / z
                        count[(w, s)] += c; total[s] += c
            t = defaultdict(lambda: 1e-6, {k: v / total[k[1]] for k, v in count.items()})
        return t
    @staticmethod
    def _cover(words, other, t):
        if not words or not other:
            return 0.0
        return sum(1.0 if w in other else max(t[(w, o)] for o in other) for w in words) / len(words)
    def __call__(self, src, tgt):
        a, b = tokens(" ".join(src)), tokens(" ".join(tgt))
        lex = (self._cover(b, a, self.t_st) + self._cover(a, b, self.t_ts)) / 2
        return 0.8 * min(1.0, lex ** 0.5) + 0.2 * self.base(src, tgt)

MOVES = [(1, 1), (1, 2), (2, 1), (2, 2), (1, 3), (3, 1), (1, 0), (0, 1)]

def align(src, tgt, scorer, skip=0.3, merge_penalty=0.2, band=None, src_types=None, tgt_types=None):
    """Find the best monotonic path through the (src x tgt) grid.
    Objective: every sentence placed in a pair earns that pair's score; every sentence left
    unaligned earns `skip`. So a 1-1 pair is taken only if its score beats `skip`, and a merge
    (1-2, 2-2...) pays `merge_penalty` per extra sentence, so it wins only when it is clearly better.
    band: only consider cells near the diagonal (speeds up long documents; None = full grid).
    src_types/tgt_types: optional segment type per sentence ('heading', 'text', 'table'...). A group
    may not mix types (a heading never merges into a sentence) and a pair of different types
    has its score halved.
    Returns [(i, a, j, b, score)] meaning src[i:i+a] <-> tgt[j:j+b] (score None for 1-0 / 0-1)."""
    n, m = len(src), len(tgt)
    st, tt = src_types or ["text"] * n, tgt_types or ["text"] * m
    if band is None and n * m > 3600:          # long stretch: search near the diagonal only
        band = max(20, int(0.3 * max(n, m)))
    memo, raw = {}, scorer
    def scorer(a, b):                          # each group pair is scored once
        k = ("\x00".join(a), "\x00".join(b))
        if k not in memo:
            memo[k] = raw(a, b)
        return memo[k]
    if hasattr(raw, "prepare"):             # batch-embed every group the DP can ask for
        groups = [" ".join(src[i:i + k]) for i in range(n) for k in (1, 2, 3) if i + k <= n]
        groups += [" ".join(tgt[j:j + k]) for j in range(m) for k in (1, 2, 3) if j + k <= m]
        raw.prepare(groups)
    NEG = float("-inf")
    best = [[NEG] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    back = {}
    for i in range(n + 1):
        for j in range(m + 1):
            if best[i][j] == NEG:
                continue
            if band and n and m and abs(i / n - j / m) * max(n, m) > band:
                continue
            for a, b in MOVES:
                if i + a > n or j + b > m:
                    continue
                if a == 0 or b == 0:
                    s, gain = None, skip
                else:
                    ga, gb = set(st[i:i + a]), set(tt[j:j + b])
                    if len(ga) > 1 or len(gb) > 1:
                        continue
                    s = scorer(src[i:i + a], tgt[j:j + b]) * (1.0 if ga == gb else 0.5)
                    gain = (a + b) * s - merge_penalty * (a + b - 2)
                if best[i][j] + gain > best[i + a][j + b]:
                    best[i + a][j + b] = best[i][j] + gain
                    back[(i + a, j + b)] = (i, j, a, b, s)
    path, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj, a, b, s = back[(i, j)]
        path.append((pi, a, pj, b, s))
        i, j = pi, pj
    return path[::-1]
