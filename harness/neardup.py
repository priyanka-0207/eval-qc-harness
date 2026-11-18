from collections import Counter, defaultdict

from .text import shingles


class ShingleIndex:
    def __init__(self, rows, n=5):
        self.n = n
        self.ids = []
        self.sets = []
        self.postings = defaultdict(list)
        for pos, r in enumerate(rows):
            s = shingles(r["narrative"], n)
            self.ids.append(r["complaint_id"])
            self.sets.append(s)
            for sh in s:
                self.postings[sh].append(pos)

    def best_match(self, narrative, exclude_id=None):
        query = shingles(narrative, self.n)
        if not query:
            return None, 0.0
        shared = Counter()
        for sh in query:
            for pos in self.postings.get(sh, ()):
                shared[pos] += 1
        best_id, best = None, 0.0
        for pos, inter in shared.items():
            if self.ids[pos] == exclude_id:
                continue
            jac = inter / (len(query) + len(self.sets[pos]) - inter)
            if jac > best:
                best_id, best = self.ids[pos], jac
        return best_id, best


def near_duplicates(eval_rows, corpus_rows, threshold, n=5):
    index = ShingleIndex(corpus_rows, n)
    hits = []
    for r in eval_rows:
        cid, jac = index.best_match(r["narrative"], exclude_id=r["complaint_id"])
        if jac >= threshold:
            hits.append({"eval_id": r["complaint_id"], "corpus_id": cid, "jaccard": round(jac, 3)})
    return hits
