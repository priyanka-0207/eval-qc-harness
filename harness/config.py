from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def use_root(base):
    global DATA, BRONZE_DIR, SILVER, GOLD, REPORTS, LABELS
    base = Path(base)
    DATA = base / "data"
    BRONZE_DIR = DATA / "bronze"
    SILVER = DATA / "silver" / "complaints.jsonl"
    GOLD = DATA / "gold"
    REPORTS = base / "reports"
    LABELS = base / "labels"


use_root(ROOT)

COLUMN_ALIASES = {
    "complaint_id": ("complaint_id", "complaint id", "id"),
    "date_received": ("date_received", "date received", "received_date", "date"),
    "product": ("product",),
    "sub_product": ("sub_product", "sub-product", "subproduct"),
    "issue": ("issue",),
    "sub_issue": ("sub_issue", "sub-issue", "subissue"),
    "company": ("company",),
    "state": ("state",),
    "tags": ("tags",),
    "narrative": (
        "narrative", "complaint_what_happened", "consumer_complaint_narrative",
        "consumer complaint narrative", "narrative_text", "text",
    ),
}
REQUIRED = ("complaint_id", "date_received", "product", "narrative")

MIN_NARRATIVE_WORDS = 20
EVAL_FRACTION = 0.25
EVAL_SIZE = 200
SEED = 7

ESCALATE_TAGS = ("Servicemember", "Older American")
FRAUD_LABEL_TERMS = ("fraud", "scam", "identity theft", "information belongs to someone else")

JUDGE_MODEL = "gpt-4o-mini"
JUDGE_KEY_NAME = "EVAL_QC_OPENAI_API_KEY"
JUDGE_SCORE_CASES = 50
JUDGE_CHECK_CASES = 20
JUDGE_REPEATS = 5

QC_MIN_CASES_PER_PRODUCT = 15
QC_MIN_CASES_PER_RULE = 10
QC_NEAR_DUP_JACCARD = 0.8
QC_MAX_DUP_RATE = 0.05
