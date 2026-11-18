import math
from collections import Counter, defaultdict

from .text import tokens


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.ids = [d["complaint_id"] for d in docs]
        self.k1, self.b = k1, b
        self.tf = []
        self.lengths = []
        df = Counter()
        for d in docs:
            counts = Counter(tokens(d["narrative"]))
            self.tf.append(counts)
            self.lengths.append(sum(counts.values()))
            df.update(counts.keys())
        n = len(docs)
        self.avg_len = sum(self.lengths) / max(n, 1)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.postings = defaultdict(list)
        for i, counts in enumerate(self.tf):
            for t in counts:
                self.postings[t].append(i)

    def search(self, query, k=10):
        scores = defaultdict(float)
        for t in set(tokens(query)):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i in self.postings[t]:
                f = self.tf[i][t]
                norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_len)
                scores[i] += idf * f * (self.k1 + 1) / (f + norm)
        top = sorted(scores.items(), key=lambda x: -x[1])[:k]
        return [(i, s) for i, s in top]
