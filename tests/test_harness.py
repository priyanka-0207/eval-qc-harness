from harness import gradercheck, qc, scorers, silver
from harness.bm25 import BM25
from harness.neardup import near_duplicates
from harness.labels import cohen_kappa

LONG = "word " * 25


def row(cid, date, product, narrative, issue="", sub_issue="", tags=""):
    return {"complaint_id": cid, "date_received": date, "product": product, "sub_product": "",
            "issue": issue, "sub_issue": sub_issue, "company": "", "state": "", "tags": tags,
            "narrative": narrative}


def silver_row(cid, date, product, narrative, rules=()):
    return {"complaint_id": cid, "date_received": date, "product": product, "tags": "",
            "narrative": narrative, "rules": list(rules), "expected_escalate": bool(rules)}


def test_silver_reconciles_and_drops(tmp_path, monkeypatch):
    monkeypatch.setattr(silver.config, "SILVER", tmp_path / "silver.jsonl")
    rows = [
        row("1", "2016-01-02", "Debt collection", "The collector called me every day about a debt " + LONG),
        row("1", "2016-01-02", "Debt collection", "The collector called me every day about a debt " + LONG),
        row("2", "2016-01-03", "Debt collection", "the collector called me EVERY day, about a debt " + LONG),
        row("3", "2016-01-04", "Credit card", "too short"),
        row("4", "", "Credit card", "no date " + LONG),
        row("5", "01/05/2016", "Credit card", "Someone opened a card in my name " + LONG,
            issue="Problem with fraud alerts", tags="Older American"),
    ]
    out, manifest = silver.build(rows)
    assert manifest["reconciled"]
    assert [r["complaint_id"] for r in out] == ["1", "5"]
    assert out[1]["date_received"] == "2016-01-05"
    assert set(out[1]["rules"]) == {"vulnerable_consumer_tag", "fraud_or_identity_theft"}


def test_near_duplicate_found_across_split():
    base = "I sent a dispute letter to the bureau and they never investigated the account " * 3
    corpus = [silver_row("c1", "2016-01-01", "A", base)]
    evals = [silver_row("e1", "2016-06-01", "A", base + " thanks"),
             silver_row("e2", "2016-06-01", "A", "completely different text about a mortgage escrow shortage " * 3)]
    hits = near_duplicates(evals, corpus, 0.8)
    assert [h["eval_id"] for h in hits] == ["e1"]


def test_qc_gate_fails_on_leaky_split():
    shared = silver_row("x", "2016-01-01", "A", "my loan servicer lost my payment again and charged fees " * 3)
    corpus = [shared]
    evals = [dict(shared)]
    result = qc.run(corpus, evals)
    failed = {c["check"] for c in result["checks"] if c["status"] == "FAIL"}
    assert result["gate"] == "FAIL"
    assert "no eval id appears in the retrieval corpus" in failed
    assert "corpus is strictly older than the eval set" in failed


def test_bm25_ranks_matching_doc_first():
    docs = [silver_row("a", "", "Mortgage", "escrow shortage on my mortgage payment"),
            silver_row("b", "", "Credit card", "late fee on my credit card statement")]
    top = BM25(docs).search("credit card late fee", k=2)
    assert docs[top[0][0]]["complaint_id"] == "b"


def test_bounded_faithfulness_rejects_shortcuts_substring_does_not():
    case = silver_row("1", "", "A", "The bank closed my account without notice. I lost access to my paycheck for two weeks. "
                      "Nobody at the branch could tell me why, and the phone line kept sending me back to the same menu.")
    whole = {"quote": case["narrative"]}
    one = {"quote": "bank"}
    good = {"quote": "I lost access to my paycheck for two weeks."}
    assert scorers.faithful_substring(one, case) and not scorers.faithful_bounded(one, case)
    assert scorers.faithful_bounded(good, case)
    assert not scorers.faithful_bounded({"quote": "I lost access to my salary for two weeks."}, case)
    assert scorers.faithful_substring(whole, case)


def test_gradercheck_reports_guardrail_blind_spot():
    cases = [
        silver_row("1", "", "A", "Someone opened an account in my name and the bureau will not remove it from my report. "
                   "I sent the police report twice and they still say it is verified.", ["fraud_or_identity_theft"]),
        silver_row("2", "", "B", "My mortgage servicer misapplied my payment and charged me a late fee this month. "
                   "I have bank records showing the payment cleared on time."),
    ]
    table = gradercheck.run(cases)
    rows = {(r["scorer"], r["probe"]): r for r in table}
    assert rows[("product_match", "planted: wrong product")]["good"]
    assert rows[("faithful_bounded", "shortcut: quote is the whole complaint")]["good"]
    assert not rows[("faithful_substring", "shortcut: one-word quote")]["good"]
    assert not rows[("guardrail", "shortcut: always escalate")]["good"]


def test_near_duplicate_handles_repeated_corpus_ids():
    text = "the servicer charged a late fee even though my payment cleared on time last month " * 2
    corpus = [silver_row("c1", "", "A", text), silver_row("c1", "", "A", text)]
    hits = near_duplicates([silver_row("e1", "", "A", text)], corpus, 0.8)
    assert hits and hits[0]["jaccard"] == 1.0


def test_borrowed_quote_that_also_appears_is_not_a_planted_mistake():
    shared = "I called customer service four times and was transferred every time."
    cases = [
        silver_row("1", "", "A", "My card was charged twice for one purchase at the store last week. " + shared),
        silver_row("2", "", "B", shared + " My mortgage escrow went up and nobody explained the new amount."),
    ]
    table = gradercheck.run(cases)
    rows = {(r["scorer"], r["probe"]): r for r in table}
    probe = rows.get(("faithful_bounded", "planted: quote from another complaint"))
    assert probe is None or probe["good"]


def test_demo_run_end_to_end(tmp_path):
    from harness import config, demo
    try:
        result = demo.run(tmp_path)
    finally:
        config.use_root(config.ROOT)
    assert result["gates"] == {"time": "PASS", "naive": "FAIL"}
    assert result["report"].exists()


class FakeClient:
    def __init__(self, ungrounded=False):
        self.calls = 0
        self.ungrounded = ungrounded

    def complete(self, system, user, temperature):
        self.calls += 1
        complaint = user.split("Complaint:\n", 1)[1].split("\n\nAgent product label:", 1)[0]
        label = user.split("Agent product label: ", 1)[1].split("\n", 1)[0]
        fits = label.split()[0].lower() in complaint.lower()
        evidence = "made up words" if self.ungrounded else " ".join(complaint.split()[:6])
        return {"score": 3 if fits else 0, "evidence": evidence, "reason": "fake"}


def test_judge_caches_and_caps_ungrounded_scores(tmp_path):
    from harness.judge import CachedJudge
    case = silver_row("1", "", "Mortgage", "My mortgage servicer raised my escrow payment without any notice or explanation at all.")
    out = {"product": "Mortgage", "quote": "raised my escrow payment"}
    client = FakeClient()
    judge = CachedJudge(client, cache_path=tmp_path / "cache.jsonl")
    first = judge.verdict(case, out)
    again = CachedJudge(client, cache_path=tmp_path / "cache.jsonl").verdict(case, out)
    assert first["passed"] and first["grounded"] and again == first
    assert client.calls == 1
    capped = CachedJudge(FakeClient(ungrounded=True), cache_path=tmp_path / "c2.jsonl").verdict(case, out)
    assert capped["raw_score"] == 3 and capped["score"] == 1 and not capped["passed"]


def test_demo_with_fake_judge_renders_dashboard(tmp_path):
    from harness import config, demo
    from harness.judge import CachedJudge
    judge = CachedJudge(FakeClient(), cache_path=tmp_path / "cache.jsonl")
    try:
        result = demo.run(tmp_path, use_judge=True, judge_client=judge)
    finally:
        config.use_root(config.ROOT)
    j = result["judge"]
    assert j["status"] == "ran" and j["scored_cases"] == config.JUDGE_SCORE_CASES
    names = {p["probe"] for p in j["probes"]}
    assert "padding: wrong product + 'approved by a senior analyst'" in names
    html = result["dashboard"].read_text(encoding="utf-8")
    assert "LLM judge" in html and "Can the judge be fooled?" in html and "Demo data." in html
    site = result["dashboard"].parent / "site"
    for page in ("data", "agent", "graders", "judge"):
        page_html = (site / page / "index.html").read_text(encoding="utf-8")
        assert f'data-start="{page}"' in page_html and 'href="#' not in page_html
    assert 'href="judge/"' in (site / "index.html").read_text(encoding="utf-8")


def test_kappa():
    assert cohen_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert abs(cohen_kappa([True, True, False, False], [True, False, True, False])) < 1e-9
