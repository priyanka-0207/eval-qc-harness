import csv
import random

from . import config

DEMO_DIR_NAME = "demo_run"
DEMO_FILE = "demo_generated_NOT_REAL.csv"

PRODUCT_LINES = {
    "Debt collection": [
        "A debt collector keeps calling me about a medical bill I already paid",
        "The collection agency will not send me validation of the debt they say I owe",
        "A collector called my workplace and threatened to sue me over an old balance",
        "They are trying to collect a debt that was discharged in my bankruptcy",
    ],
    "Credit card": [
        "My credit card company charged me interest after I paid the statement balance in full",
        "The card issuer raised my credit limit fee without telling me",
        "I disputed a charge on my credit card and the bank closed the dispute without a reason",
        "My credit card rewards points were taken away after I paid off the card",
    ],
    "Mortgage": [
        "My mortgage servicer added an escrow shortage and raised my monthly payment",
        "The servicer lost my loan modification paperwork for the third time",
        "My mortgage payment was applied to the wrong month and I was charged a late fee",
        "The lender started foreclosure while my modification was still under review",
    ],
    "Checking or savings account": [
        "The bank froze my checking account and will not tell me why",
        "I was charged overdraft fees on transactions that cleared with money in the account",
        "My savings account was closed and the bank is holding my funds",
        "A deposit to my checking account has been on hold for two weeks",
    ],
    "Student loan": [
        "My student loan servicer put my loans in forbearance without asking me",
        "The servicer is not counting my payments toward loan forgiveness",
        "My student loan payment amount changed after I submitted my income paperwork",
        "The student loan company applied my extra payment to interest instead of principal",
    ],
    "Credit reporting or other personal consumer reports": [
        "The credit bureau is reporting a late payment that never happened",
        "My credit report shows an account with the wrong balance",
        "The bureau did not investigate my dispute and marked it verified",
        "My credit report lists an address where I have never lived",
    ],
}

CONFUSABLE = {
    "Debt collection": "The collector also put this account on my credit report.",
    "Credit reporting or other personal consumer reports": "The account was sold to a collection agency.",
    "Credit card": "The bank also reported the balance to the credit bureaus.",
    "Checking or savings account": "My debit card was declined at the store.",
}

GENERAL = [
    "I called customer service four times and was transferred every time.",
    "I have sent letters and emails and nobody has answered me.",
    "I waited on hold for over an hour and the call dropped.",
    "The representative told me there was nothing they could do.",
    "This has hurt my budget and I am behind on other bills now.",
    "I have records of every payment and every call.",
    "I want the company to correct this and explain what happened.",
    "I asked for a supervisor and was told to call back later.",
]

FRAUD_EXPLICIT = "I am a victim of identity theft and someone used my information."
FRAUD_IMPLICIT = "This account is not mine and I never opened it."

TEMPLATE_LETTERS = [
    "I am writing to dispute the following information in my file. The items listed are inaccurate and "
    "incomplete. Under the Fair Credit Reporting Act you are required to investigate and remove any "
    "information that cannot be verified. Please delete these items and send me an updated copy of my report.",
    "This letter is a formal request for validation of the alleged debt. I do not acknowledge that I owe "
    "this amount. Please provide the original signed contract and a full payment history. Until you validate "
    "this debt you must stop all collection activity and remove it from my credit file.",
]


def _narrative(rng, product):
    parts = [rng.choice(PRODUCT_LINES[product]) + "."]
    if product in CONFUSABLE and rng.random() < 0.5:
        parts.append(CONFUSABLE[product])
    parts += rng.sample(GENERAL, 3)
    rng.shuffle(parts)
    return " ".join(parts)


def generate(path, n=1500, seed=11):
    rng = random.Random(seed)
    products = list(PRODUCT_LINES)
    rows = []
    for i in range(n):
        product = rng.choice(products)
        month, day = rng.randint(1, 12), rng.randint(1, 28)
        issue, sub_issue, tags = "Other issue", "", rng.choice(["", "", "", "", "", "Older American", "Servicemember"])
        roll = rng.random()
        if roll < 0.12:
            letter = rng.randrange(len(TEMPLATE_LETTERS))
            product = ("Credit reporting or other personal consumer reports" if letter == 0 else "Debt collection")
            text = TEMPLATE_LETTERS[letter] + " " + rng.choice(GENERAL)
        else:
            text = _narrative(rng, product)
            if roll < 0.20:
                text = FRAUD_EXPLICIT + " " + text
                issue, sub_issue = "Fraud or scam", "Identity theft"
            elif roll < 0.27:
                text = FRAUD_IMPLICIT + " " + text
                issue, sub_issue = "Incorrect information on your report", "Information belongs to someone else"
        if rng.random() < 0.06:
            product = rng.choice([p for p in products if p != product])
        if rng.random() < 0.02:
            text = "Please fix my account."
        date = "" if rng.random() < 0.01 else f"2016-{month:02d}-{day:02d}"
        rows.append({"complaint_id": str(500000 + i), "date_received": date, "product": product,
                     "sub_product": "", "issue": issue, "sub_issue": sub_issue, "company": "Demo Company",
                     "state": rng.choice(["MA", "NY", "TX", "CA", "OH"]), "tags": tags, "narrative": text})
    rows += [dict(r) for r in rng.sample(rows, n // 30)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


def run(base=None, use_judge=False, judge_client=None):
    base = base or config.ROOT / DEMO_DIR_NAME
    config.use_root(base)
    generate(config.BRONZE_DIR / DEMO_FILE)
    from .cli import run_all
    return run_all(use_judge=use_judge, judge_client=judge_client)
