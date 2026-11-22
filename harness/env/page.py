import json

from .. import config, store
from ..dashboard import CSS, _chip, _e, _nice_time, _table
from ..landing import JS, LANDING_CSS
from . import run as env_run

FAMILY_INFO = (
    ("tickets", "Support tickets",
     "The agent resolves a damaged-item ticket with six tools: get_policy, get_customer, list_orders, issue_refund, "
     "escalate and reply.",
     "The right refund for the right amount, or a reply, or an escalation, and nothing else."),
    ("dataqc", "Data QC",
     "The agent queries a payments table in read-only SQLite and flags every row that breaks a rule in the spec.",
     "The flagged rows match the bad rows exactly."),
    ("retrieval", "Help center retrieval",
     "The agent searches help center pages, reads one, and answers with the page id, the value and a 5 to 40 word "
     "quote copied from that page.",
     "Right page, right value, and a quote that is really on the page and contains the value."),
)

SHORTCUT_INFO = (
    ("null", "Does nothing and submits"),
    ("always_escalate", "Escalates every ticket"),
    ("reply_only", "Sends a polite reply and never acts"),
    ("refund_all_orders", "Refunds every order the customer has"),
    ("flag_all", "Flags every row in the table"),
    ("flag_last_rows", "Flags the last three rows"),
    ("whole_doc_quote", "Quotes the entire page as evidence"),
    ("echo_question", "Answers with the question itself"),
)

PAGE_CSS = """
.tiles3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px}
@media (max-width:860px){.tiles3{grid-template-columns:1fr}}
.tiles3 .tile{padding:16px 18px;border-top:4px solid var(--clean)}
.tiles3 .tile p{margin:6px 0 0;font-size:14px;color:var(--ink-2)}
.tiles3 .tile .reward{margin-top:10px;padding-top:8px;border-top:1px solid var(--grid)}
.tiles3 .tile .reward b{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink)}
.caught{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
@media (max-width:960px){.caught{grid-template-columns:1fr}}
.caught .card{border-top:4px solid var(--crit)}
.caught .quote{margin-top:8px}
mark{background:var(--crit-tint);color:inherit;padding:0 2px;border-radius:3px}
pre.trace{background:var(--page);border:1px solid var(--border);border-radius:6px;padding:12px 14px;overflow-x:auto;font:12px/1.6 "IBM Plex Mono",ui-monospace,Consolas,monospace;margin:8px 0 0;white-space:pre}
"""


def _rate(cell):
    return f"{cell['passed']}/{cell['tasks']}" if cell else "&ndash;"


def _status(check):
    return _chip("good", "Pass") if check["status"] == "PASS" else _chip("crit", "Fail")


def _gate_table(clean, dirty):
    rows = []
    for c, d in zip(clean["gate"]["checks"], dirty["gate"]["checks"]):
        rows.append([_e(c["check"].capitalize()),
                     f'{_status(c)}<div class="how">{_e(c["detail"])}</div>',
                     f'{_status(d)}<div class="how">{_e(d["detail"])}</div>'])
    return _table(["Check", f"Clean set ({clean['task_count']} tasks)",
                   f"With 3 planted bad tasks ({dirty['task_count']} tasks)"], rows)


def _mark(text, needle):
    i = text.lower().find(needle.lower())
    if i < 0:
        return _e(text)
    return _e(text[:i]) + f"<mark>{_e(text[i:i + len(needle)])}</mark>" + _e(text[i + len(needle):])


def _caught(dirty, tasks):
    by_id = {t["id"]: t for fam in tasks.values() for t in fam}
    cards = []
    for leak in dirty["gate"].get("leaks", []):
        t = by_id[leak["task_id"]]
        cards.append(f"""<section class="card"><h3>Answer leaked in the prompt</h3>
<p class="how">Task <code>{_e(t["id"])}</code>. The answer, <strong>{_e(", ".join(leak["leaked"]))}</strong>, is written
into the question, so an agent can copy it without reading a single page.</p>
<div class="quote">{_mark(t["prompt"], leak["leaked"][0])}</div></section>""")
    for hack in dirty["gate"].get("hacks", []):
        t = by_id[hack["task_id"]]
        bad = t["hidden"]["bad_rows"]
        flagged = hack["answer"].get("flagged", [])
        cards.append(f"""<section class="card"><h3>Reward too lenient</h3>
<p class="how">Task <code>{_e(t["id"])}</code>. Only {len(bad)} rows break a rule (rows {_e(", ".join(map(str, bad)))}).
The reward only checked that those rows were somewhere in the flagged list, so the <code>{_e(hack["agent"])}</code>
shortcut flagged all {len(flagged)} rows and was paid for it.</p>
<div class="outcome"><div class="before"><b>Lenient reward</b>Flagging every row passes.</div>
<div class="after"><b>Exact reward</b>The flagged rows must equal the bad rows.</div></div></section>""")
    for dup in dirty["gate"].get("duplicates", []):
        a, b = by_id[dup["a"]], by_id[dup["b"]]
        cards.append(f"""<section class="card"><h3>Duplicated task</h3>
<p class="how">Tasks <code>{_e(a["id"])}</code> and <code>{_e(b["id"])}</code> share the same data, and their prompts
overlap {dup["jaccard"]:.0%} by 3-word phrases. Counting both gives one case double weight in every pass rate.</p>
<div class="quote">{_e(a["prompt"])}</div><div class="quote">{_e(b["prompt"])}</div></section>""")
    return '<div class="caught">' + "".join(cards) + "</div>"


def _shortcut_table(clean):
    rates = clean["pass_rates"]
    rows = []
    for name, what in SHORTCUT_INFO:
        if name in rates:
            rows.append([f"<code>{_e(name)}</code>", _e(what), _rate(rates[name]["all"])])
    return _table(["Shortcut agent", "What it does", "Tasks passed"], rows, num_cols=(2,))


def _regression(clean):
    rates = clean["pass_rates"]
    fams = [f for f, *_ in FAMILY_INFO]
    rows = [[_e(a)] + [_rate(rates[a].get(f)) for f in fams] + [_rate(rates[a]["all"])] for a in ("v1", "v2")]
    table = _table(["Agent"] + [label for _, label, *_ in FAMILY_INFO] + ["All"], rows, num_cols=(1, 2, 3, 4))
    reg = clean["regression"]
    ex = clean.get("example")
    trace = ""
    if ex:
        lines = []
        for s in ex["steps"]:
            obs = s["obs"].get("result", s["obs"].get("error"))
            lines.append(f"{s['step']}. {s['tool']} {json.dumps(s['args'])} -> {json.dumps(obs)[:110]}")
        trace = f"""<p class="how" style="margin-top:12px">Trace of <code>{_e(ex["agent"])}</code> on
<code>{_e(ex["task_id"])}</code> (reward {ex["reward"]}). The rice cooker was delivered 30 days ago, and the policy
refunds damage reported within 30 days. v2 compares with "under 30" instead of "30 or fewer", so it refuses a refund
the policy allows. v1 refunded and passed.</p><pre class="trace">{_e(chr(10).join(lines))}</pre>"""
    return f"""{table}
<div class="outcome"><div class="after"><b>Fixed: {len(reg["fixed"])} tasks</b>{_e(", ".join(reg["fixed"]))}</div>
<div class="before"><b>Broken: {len(reg["broken"])} task</b>{_e(", ".join(reg["broken"]) or "none")}</div></div>{trace}"""


def render(clean, dirty, tasks):
    fam_tiles = "".join(
        f"""<div class="tile"><div class="label">{_e(label)} &middot; {clean["tasks_per_family"].get(key, 0)} tasks</div>
<p>{_e(what)}</p><div class="reward"><b>Reward pays only for</b><p>{_e(pays)}</p></div></div>"""
        for key, label, what, pays in FAMILY_INFO)
    sitebar = ('<nav class="sitebar"><a href="../">Overview</a><a href="../real/">Real CFPB run</a><a href="../synthetic/">Synthetic run</a>'
               '<a href="./" class="on">RL environment</a></nav>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RL Environment | Eval QC Harness</title>
<meta name="description" content="30 tasks with code-checked rewards and a QC gate that catches leaked answers, lenient rewards and duplicated tasks.">
<style>{CSS}{LANDING_CSS}{PAGE_CSS}</style></head>
<body>
<header class="topbar"><div class="inner">{sitebar}<div class="row"><div>
<div class="eyebrow">Eval QC harness</div><h1>Can this reward be trusted?</h1>
<p class="meta">RL environment &middot; {clean["task_count"]} tasks in 3 families &middot; every reward is code &middot;
generated {_e(_nice_time(clean["generated_at"]))}</p></div>
<button class="theme" id="theme" type="button">Dark theme</button></div>
<div style="height:22px"></div></div></header>
<main class="wrap">
<div class="banner"><strong>Synthetic tasks, scripted agents.</strong> The tasks are generated, and the agents are short
Python scripts, not language models. The page shows what the task gate catches and how the rewards behave, not model
performance.</div>

<h2>The tasks</h2>
<div class="tiles3">{fam_tiles}</div>

<section class="card"><h3>Task QC gate</h3>
<p class="sub">The gate runs before any agent is scored. It plays a reference solution, an agent that does nothing, and
seven shortcut agents on every task, then checks the tasks themselves. Three bad tasks were planted in the second set
to show what it catches.</p>
{_gate_table(clean, dirty)}</section>

<h2>Caught by the gate</h2>
{_caught(dirty, tasks)}

<div class="grid2">
<section class="card"><h3>Shortcut agents on the clean set</h3>
<p class="sub">A reward that pays a shortcut is a reward an RL run will learn to game.</p>
{_shortcut_table(clean)}
<p class="how" style="margin-top:8px">The 6 shortcut passes all give the reference answer: escalating is the right call
on 3 tickets, and replying is right on 3 others. None is a wrong answer that got paid.</p></section>
<section class="card"><h3>Regression report: v1 to v2</h3>
<p class="sub">Every change is compared task by task, so one broken case is visible even when the total goes up.</p>
{_regression(clean)}</section>
</div>

<section class="card"><h3>Try it</h3><p class="sub">It needs Python 3.10 or newer and nothing else.</p>
<pre class="try">git clone {config.REPO_URL}
cd eval-qc-harness
python -m harness env
python -m harness env --dirty --ci</pre>
<p class="how" style="margin-top:8px"><code>--ci</code> exits 1 when the task gate fails, so a bad task set can block a
merge. Per-step traces for every agent are written to <code>reports/env/traces</code>.</p></section>
<footer><a href="{config.REPO_URL}">Source on GitHub</a></footer>
</main><script>{JS}</script></body></html>"""


def build(out_path):
    base = config.REPORTS
    clean_p, dirty_p = base / "env" / "results.json", base / "env_dirty" / "results.json"
    if not (clean_p.exists() and dirty_p.exists()):
        return None
    clean, dirty = store.read_json(clean_p), store.read_json(dirty_p)
    html = render(clean, dirty, env_run.build_tasks(dirty=True))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
