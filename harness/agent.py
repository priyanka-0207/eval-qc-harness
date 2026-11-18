from collections import defaultdict

from . import config
from .bm25 import BM25
from .text import sentences, tokens

V1_FRAUD_WORDS = ("fraud", "identity theft", "scam")
V2_FRAUD_WORDS = V1_FRAUD_WORDS + (
    "stolen", "not mine", "never opened", "did not open", "didn't open", "unauthorized",
    "do not recognize", "don't recognize", "someone opened", "without my permission",
)
MAX_QUOTE_WORDS = 40


def _tag_escalation(case):
    return any(t.lower() in (case.get("tags") or "").lower() for t in config.ESCALATE_TAGS)


def _clip(sentence):
    words = sentence.split()
    return " ".join(words[:MAX_QUOTE_WORDS])


class Agent:
    name = "base"

    def __init__(self, corpus):
        self.corpus = corpus
        self.index = BM25(corpus)

    def retrieve(self, narrative, k):
        return [(self.corpus[i], s) for i, s in self.index.search(narrative, k)]

    def run(self, case):
        raise NotImplementedError


class NearestNeighborAgent(Agent):
    name = "v1_nearest"

    def run(self, case):
        hits = self.retrieve(case["narrative"], 1)
        product = hits[0][0]["product"] if hits else None
        text = case["narrative"].lower()
        escalate = _tag_escalation(case) or any(w in text for w in V1_FRAUD_WORDS)
        first = sentences(case["narrative"])
        return {
            "complaint_id": case["complaint_id"],
            "product": product,
            "escalate": escalate,
            "quote": _clip(first[0]) if first else "",
            "retrieved": [h[0]["complaint_id"] for h in hits],
        }


class VotingAgent(Agent):
    name = "v2_vote"

    def __init__(self, corpus, k=9):
        super().__init__(corpus)
        self.k = k

    def run(self, case):
        hits = self.retrieve(case["narrative"], self.k)
        votes = defaultdict(float)
        for doc, score in hits:
            votes[doc["product"]] += score
        product = max(votes, key=votes.get) if votes else None
        text = case["narrative"].lower()
        escalate = _tag_escalation(case) or any(w in text for w in V2_FRAUD_WORDS)
        neighbor_terms = set()
        for doc, _ in hits[:3]:
            neighbor_terms.update(tokens(doc["narrative"]))
        best, best_score = "", -1.0
        for s in sentences(case["narrative"]):
            if len(s.split()) < 5:
                continue
            score = sum(self.index.idf.get(t, 0.0) for t in set(tokens(s)) & neighbor_terms)
            if score > best_score:
                best, best_score = s, score
        return {
            "complaint_id": case["complaint_id"],
            "product": product,
            "escalate": escalate,
            "quote": _clip(best),
            "retrieved": [h[0]["complaint_id"] for h in hits],
        }


AGENTS = {a.name: a for a in (NearestNeighborAgent, VotingAgent)}


def run_agent(name, corpus, eval_rows):
    agent = AGENTS[name](corpus)
    return [agent.run(case) for case in eval_rows]
