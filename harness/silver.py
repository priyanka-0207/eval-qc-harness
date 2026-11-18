import re
from datetime import datetime

from . import config, store
from .text import normalize, squash, word_count

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d")


def parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    head = re.split(r"[T ]", value, maxsplit=1)[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(head, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def rule_hits(row):
    hits = []
    tags = row.get("tags", "")
    if any(t.lower() in tags.lower() for t in config.ESCALATE_TAGS):
        hits.append("vulnerable_consumer_tag")
    issue_text = f"{row.get('issue', '')} {row.get('sub_issue', '')}".lower()
    if any(term in issue_text for term in config.FRAUD_LABEL_TERMS):
        hits.append("fraud_or_identity_theft")
    return hits


def build(bronze_rows):
    steps = [{"step": "bronze rows", "rows": len(bronze_rows), "dropped": 0}]

    def record(name, kept, before):
        steps.append({"step": name, "rows": len(kept), "dropped": before - len(kept)})

    rows = []
    for r in bronze_rows:
        date = parse_date(r["date_received"])
        if r["complaint_id"] and r["product"] and r["narrative"].strip() and date:
            rows.append({**r, "date_received": date})
    record("drop missing id, product, narrative or date", rows, len(bronze_rows))

    before = len(rows)
    rows = [r for r in rows if word_count(r["narrative"]) >= config.MIN_NARRATIVE_WORDS]
    record(f"drop narratives under {config.MIN_NARRATIVE_WORDS} words", rows, before)

    before = len(rows)
    rows.sort(key=lambda r: (r["date_received"], r["complaint_id"]))
    seen_ids, kept = set(), []
    for r in rows:
        if r["complaint_id"] not in seen_ids:
            seen_ids.add(r["complaint_id"])
            kept.append(r)
    rows = kept
    record("drop repeated complaint ids", rows, before)

    before = len(rows)
    seen_text, kept, dup_examples = {}, [], []
    for r in rows:
        key = normalize(r["narrative"])
        if key in seen_text:
            if len(dup_examples) < 5:
                dup_examples.append({"kept": seen_text[key], "dropped": r["complaint_id"]})
            continue
        seen_text[key] = r["complaint_id"]
        kept.append(r)
    rows = kept
    record("drop exact duplicate narratives (after redaction and punctuation removed)", rows, before)

    silver = []
    for r in rows:
        hits = rule_hits(r)
        silver.append({
            "complaint_id": r["complaint_id"],
            "date_received": r["date_received"],
            "product": r["product"],
            "sub_product": r["sub_product"],
            "issue": r["issue"],
            "sub_issue": r["sub_issue"],
            "company": r["company"],
            "state": r["state"],
            "tags": r["tags"],
            "narrative": squash(r["narrative"]),
            "rules": hits,
            "expected_escalate": bool(hits),
        })

    reconciled = steps[0]["rows"] - sum(s["dropped"] for s in steps[1:]) == len(silver)
    manifest = {"steps": steps, "reconciled": reconciled, "duplicate_examples": dup_examples}
    store.write_jsonl(config.SILVER, silver)
    store.write_json(config.SILVER.parent / "manifest.json", manifest)
    return silver, manifest
