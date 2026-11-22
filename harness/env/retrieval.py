import copy
import re

from ..bm25 import BM25
from .core import ToolError

NAME = "retrieval"
OUTCOMES = ("variant_a", "variant_b")
QUOTE_MIN, QUOTE_MAX = 5, 40
SEARCH_K = 5

INTRO = "This help center page from Harbor Bank explains {topic_lower} and what customers should expect."
FILLERS = ("Terms can change, and the latest version always appears in the account agreement.",
           "If you have questions, the support team can review your account by phone or in a branch.",
           "Fees and limits shown here apply to accounts opened in the United States.")

TOPICS = [
    ("Card dispute window", "dispute window", [("personal credit cards", "60 days"), ("business credit cards", "90 days")]),
    ("Wire transfer cutoff", "same-day cutoff", [("domestic wires", "5 p.m. Eastern"), ("international wires", "3 p.m. Eastern")]),
    ("Overdraft fee", "overdraft fee", [("standard checking accounts", "$34"), ("student checking accounts", "$15")]),
    ("ATM withdrawal limit", "daily ATM limit", [("standard debit cards", "$800"), ("premier debit cards", "$1,500")]),
    ("Check hold period", "hold period", [("new accounts", "7 business days"), ("established accounts", "2 business days")]),
    ("Card replacement time", "delivery time", [("standard card replacement", "7 to 10 business days"), ("expedited card replacement", "2 business days")]),
    ("Stop payment fee", "stop payment fee", [("stop payments requested by phone", "$30"), ("stop payments requested online", "$20")]),
    ("Foreign transaction fee", "foreign transaction fee", [("travel rewards cards", "0%"), ("cash back cards", "3%")]),
    ("Account closing notice", "notice period", [("savings accounts", "30 days"), ("certificates of deposit", "10 days")]),
    ("Statement copy fee", "fee per copy", [("paper statement copies", "$5"), ("electronic statement copies", "$0")]),
]

NOISE = [
    ("Mobile check deposit", "Mobile check deposit lets you photograph a check in the app. Deposits made before 9 p.m. Eastern post the same business day. Endorse the back of the check and write for mobile deposit only before you take the photo."),
    ("Password reset", "You can reset your online banking password from the sign in page. A one-time code is sent to the phone number on file and expires after 10 minutes. After three failed codes the reset is locked for one hour."),
    ("Branch hours", "Most branches open at 9 a.m. and close at 5 p.m. on weekdays. Selected branches also open on Saturday mornings. Holiday hours are posted on each branch page a week before the holiday."),
    ("Zelle limits", "Zelle payments are limited by account age and history. New customers can send up to $500 per day while established customers can send more. Payments to new recipients may be held for review."),
    ("Travel notice", "You no longer need to file a travel notice before using your card abroad. Our fraud system recognizes travel patterns automatically. Keep your phone number current so we can reach you if a charge looks unusual."),
]


def _key_sentence(qualifier, thing, value):
    return f"For {qualifier}, the {thing} is {value}."


def build_corpus():
    docs = []
    for t, (topic, thing, variants) in enumerate(TOPICS):
        for v, (qualifier, value) in enumerate(variants):
            text = " ".join([INTRO.format(topic_lower=topic.lower()), _key_sentence(qualifier, thing, value), *FILLERS])
            docs.append({"doc_id": f"doc-{t * 2 + v + 1:02d}", "title": f"{topic}: {qualifier}", "text": text})
    for n, (title, text) in enumerate(NOISE):
        docs.append({"doc_id": f"doc-{len(TOPICS) * 2 + n + 1:02d}", "title": title, "text": text})
    return docs


def _prompt(thing, qualifier):
    return (f"Customer question: What is the {thing} for {qualifier}? Find the help center page that answers it, "
            f"then call answer with the doc_id, the value, and a quote of {QUOTE_MIN} to {QUOTE_MAX} words copied "
            "from that page.")


def make_tasks(dirty=False, seed=7):
    corpus = build_corpus()
    tasks = []
    for t, (topic, thing, variants) in enumerate(TOPICS):
        v = (t + seed) % 2
        qualifier, value = variants[v]
        tasks.append({
            "id": f"retrieval-{t + 1:02d}", "family": NAME,
            "prompt": _prompt(thing, qualifier),
            "spec": {"quote_words": [QUOTE_MIN, QUOTE_MAX]},
            "data": {"corpus": corpus},
            "hidden": {"doc_id": f"doc-{t * 2 + v + 1:02d}", "value": value,
                       "quote": _key_sentence(qualifier, thing, value), "variant": OUTCOMES[v]},
        })
    if dirty:
        qualifier, value = TOPICS[0][2][1]
        tasks.append({
            "id": "retrieval-dirty-leak", "family": NAME,
            "prompt": (f"Customer question: Is the dispute window for {qualifier} {value}? Find the help center page "
                       f"that answers it, then call answer with the doc_id, the value, and a quote of {QUOTE_MIN} to "
                       f"{QUOTE_MAX} words copied from that page."),
            "spec": {"quote_words": [QUOTE_MIN, QUOTE_MAX]},
            "data": {"corpus": corpus},
            "hidden": {"doc_id": "doc-02", "value": value,
                       "quote": _key_sentence(qualifier, "dispute window", value), "variant": OUTCOMES[1]},
        })
    return tasks


def initial_state(task):
    corpus = copy.deepcopy(task["data"]["corpus"])
    index = BM25([{"complaint_id": d["doc_id"], "narrative": f"{d['title']} {d['text']}"} for d in corpus])
    return {"corpus": {d["doc_id"]: d for d in corpus}, "order": [d["doc_id"] for d in corpus],
            "index": index, "answer": None}


def apply(state, tool, args):
    if tool == "search":
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolError("query is empty")
        hits = state["index"].search(query, k=SEARCH_K)
        return [{"doc_id": state["order"][i], "title": state["corpus"][state["order"][i]]["title"]} for i, _ in hits]
    if tool == "read":
        doc = state["corpus"].get(args.get("doc_id"))
        if doc is None:
            raise ToolError(f"no document {args.get('doc_id')}")
        return copy.deepcopy(doc)
    if tool == "answer":
        state["answer"] = {"doc_id": str(args.get("doc_id", "")), "value": str(args.get("value", "")),
                           "quote": str(args.get("quote", ""))}
        return "answer recorded"
    raise ToolError(f"unhandled tool {tool}")


TOOLS = {
    "search": "args: query. Return the top 5 help center pages as doc_id and title.",
    "read": "args: doc_id. Return the full page text.",
    "answer": "args: doc_id, value, quote. Record the final answer. The last call wins.",
}


def _norm(s):
    return " ".join(s.lower().strip().rstrip(".").split())


def final_answer(state):
    return copy.deepcopy(state["answer"])


def reward(task, state):
    a = state["answer"]
    if not a:
        return 0
    h = task["hidden"]
    doc = state["corpus"].get(a["doc_id"])
    if a["doc_id"] != h["doc_id"] or doc is None:
        return 0
    if _norm(a["value"]) != _norm(h["value"]):
        return 0
    quote = " ".join(a["quote"].split())
    words = len(quote.split())
    if not QUOTE_MIN <= words <= QUOTE_MAX:
        return 0
    if quote not in " ".join(doc["text"].split()):
        return 0
    return int(_norm(h["value"]) in _norm(quote))


def close(state):
    pass


def outcome(task):
    return [task["hidden"]["variant"]]


def leak_strings(task):
    return [task["hidden"]["value"], task["hidden"]["doc_id"]]


def _value_sentence(text, must_contain=None):
    for s in re.split(r"(?<=\.)\s+", text):
        if " is " in s and (must_contain is None or must_contain in s.lower()):
            m = re.search(r" is (.+)\.$", s)
            if m:
                return s, m.group(1)
    return None, ""


def oracle(task):
    h = task["hidden"]

    def agent(start):
        yield {"tool": "answer", "args": {"doc_id": h["doc_id"], "value": h["value"], "quote": h["quote"]}}
        yield {"tool": "submit"}
    return agent


def _parse_question(prompt):
    m = re.search(r"What is the (.+?) for (.+?)\?", prompt)
    return (m.group(1), m.group(2)) if m else ("", "")


def v1_top_hit(start):
    thing, _ = _parse_question(start["prompt"])
    hits = (yield {"tool": "search", "args": {"query": thing or start["prompt"]}})["result"]
    if not hits:
        return
    doc = (yield {"tool": "read", "args": {"doc_id": hits[0]["doc_id"]}})["result"]
    sentence, value = _value_sentence(doc["text"])
    yield {"tool": "answer", "args": {"doc_id": doc["doc_id"], "value": value, "quote": sentence or ""}}
    yield {"tool": "submit"}


def v2_read_and_match(start):
    _, qualifier = _parse_question(start["prompt"])
    question = start["prompt"].split("?")[0]
    hits = (yield {"tool": "search", "args": {"query": question}})["result"]
    for hit in hits[:3]:
        doc = (yield {"tool": "read", "args": {"doc_id": hit["doc_id"]}})["result"]
        sentence, value = _value_sentence(doc["text"], must_contain=qualifier.lower())
        if sentence:
            yield {"tool": "answer", "args": {"doc_id": doc["doc_id"], "value": value, "quote": sentence}}
            break
    yield {"tool": "submit"}


def whole_doc_quote(start):
    hits = (yield {"tool": "search", "args": {"query": start["prompt"].split("?")[0]}})["result"]
    doc = (yield {"tool": "read", "args": {"doc_id": hits[0]["doc_id"]}})["result"]
    _, value = _value_sentence(doc["text"])
    yield {"tool": "answer", "args": {"doc_id": doc["doc_id"], "value": value, "quote": doc["text"]}}
    yield {"tool": "submit"}


def echo_question(start):
    hits = (yield {"tool": "search", "args": {"query": start["prompt"].split("?")[0]}})["result"]
    question = start["prompt"].split("?")[0] + "?"
    yield {"tool": "answer", "args": {"doc_id": hits[0]["doc_id"], "value": "", "quote": question}}
    yield {"tool": "submit"}


AGENTS = {"v1": v1_top_hit, "v2": v2_read_and_match}
SHORTCUTS = {"whole_doc_quote": whole_doc_quote, "echo_question": echo_question}
