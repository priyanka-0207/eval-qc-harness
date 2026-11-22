from . import config
from .dashboard import CSS, _e

REPO_URL = config.REPO_URL

LANDING_CSS = """
.hero h1{font-size:32px;line-height:1.2;margin:4px 0 8px;max-width:760px}
.hero .lede{color:var(--top-muted);font-size:17px;max-width:720px;margin:0 0 18px}
.links{display:flex;flex-wrap:wrap;gap:8px;padding-bottom:22px}
.links a{color:var(--top-ink);text-decoration:none;font-size:14px;font-weight:600;border:1px solid rgba(255,255,255,.25);border-radius:6px;padding:8px 14px}
.links a.primary{background:var(--top-ink);color:var(--top);border-color:var(--top-ink)}
.links a:hover{border-color:var(--top-ink)}
.run-label{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.big3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px}
@media (max-width:860px){.big3{grid-template-columns:1fr}}
.big3 .tile{padding:16px 18px;border-top:4px solid var(--clean)}
.big3 .tile.crit{border-top-color:var(--crit)}.big3 .tile.good{border-top-color:var(--good)}
.big3 .value{font-size:31px;line-height:1.15;margin:6px 0 4px}
.big3 .value small{font-size:16px;font-weight:600;color:var(--ink-2)}
.big3 .note{font-size:14px;color:var(--ink-2)}
.rates{list-style:none;margin:8px 0 0;padding:0}
.rates li{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-top:1px solid var(--grid);font-size:14px}
.rates li:first-child{border-top:0}
.rates b{font-variant-numeric:tabular-nums;font-size:16px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px}
@media (max-width:700px){.pair{grid-template-columns:1fr}}
.quote{background:var(--page);border:1px solid var(--border);border-radius:6px;padding:12px 14px;font-size:14px;color:var(--ink-2)}
.quote .who{font-size:13px;font-weight:600;color:var(--ink);margin-bottom:6px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.outcome{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
@media (max-width:700px){.outcome{grid-template-columns:1fr}}
.outcome div{border-radius:6px;padding:10px 14px;font-size:14px}
.outcome .before{background:var(--crit-tint)}.outcome .after{background:var(--good-tint)}
.outcome b{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px}
pre.try{background:var(--top);color:var(--top-ink);border-radius:8px;padding:14px 16px;white-space:pre-wrap;word-break:break-all;font:13px/1.6 "IBM Plex Mono",ui-monospace,Consolas,monospace;margin:8px 0 0}
ul.plain{margin:6px 0 0;padding-left:18px;color:var(--ink-2)}
ul.plain li{margin:3px 0}
footer a{color:var(--ink-2)}
"""

JS = """
(function(){
var root=document.documentElement,btn=document.getElementById('theme');
function current(){return root.dataset.theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')}
function label(){btn.textContent=current()==='dark'?'Light theme':'Dark theme'}
try{var saved=localStorage.getItem('evalqc-theme');if(saved)root.dataset.theme=saved}catch(e){}
label();
try{matchMedia('(prefers-color-scheme: dark)').addEventListener('change',label)}catch(e){}
btn.addEventListener('click',function(){root.dataset.theme=current()==='dark'?'light':'dark';try{localStorage.setItem('evalqc-theme',root.dataset.theme)}catch(e){}label()});
})();
"""


def _pct(r):
    return "n/a" if r is None or r.get("rate") is None else f"{r['rate'] * 100:.0f}%"


def _frac(r):
    return "" if r is None else f"{r['passed']} of {r['n']}"


def _step_note(h):
    s = h["blocked_by_step"]
    parts = []
    for key, label in (("drop exact duplicate narratives", "duplicates"),
                       ("drop repeated complaint ids", "repeated ids"),
                       ("drop narratives under", "too short"),
                       ("drop missing", "missing fields")):
        n = sum(v for k, v in s.items() if k.startswith(key))
        if n:
            parts.append(f"{n:,} {label}")
    return ", ".join(parts) if parts else "nothing to drop"


def _example(h):
    ex = h.get("example")
    if not ex:
        return ('<section class="card"><h3>Caught case</h3><p class="sub">No near copies crossed the naive split '
                'in this run, so there is no leaked example to show.</p></section>')
    leak, rest = h.get("naive_v1_on_leaked"), h.get("naive_v1_on_clean")
    if ex["agent_top1_is_twin"] and ex["agent_correct"]:
        agent_line = "The agent found the twin and copied its label." 
    elif ex["agent_top1_is_twin"]:
        agent_line = "The agent found the twin and copied its label." 
    else:
        agent_line = "The twin is in the corpus the agent searches." 
    leak_line = (f" Across the random split, the agent got {_frac(leak)} leaked cases right ({_pct(leak)}) "
                 f"and {_pct(rest)} of the rest." if leak and rest else "")
    return f"""<section class="card">
<div class="split-head"><div><h3>Caught: two near-identical complaints</h3>
<p class="how">{ex["jaccard"]:.0%} the same wording</p></div></div>
<div class="pair">
<div class="quote"><div class="who"><span>Test case #{_e(ex["eval_id"])}</span><span class="muted">{_e(ex["eval_date"])} &middot; {_e(ex["eval_product"])}</span></div>{_e(ex["eval_text"])}</div>
<div class="quote"><div class="who"><span>Corpus complaint #{_e(ex["corpus_id"])}</span><span class="muted">{_e(ex["corpus_date"])} &middot; {_e(ex["corpus_product"])}</span></div>{_e(ex["corpus_text"])}</div>
</div>
<div class="outcome">
<div class="before"><b>Random split</b>{agent_line}</div>
<div class="after"><b>With the gate</b>Near copies are removed, so the agent has to read the complaint.</div>
</div></section>"""


def render(h, has_real, has_synthetic, video_url=None, has_env=False):
    video_url = config.DEMO_VIDEO_URL if video_url is None else video_url
    real = h["dataset"] == "real"
    a = h["agent"]
    run_title = (f'Real CFPB complaints, {h["eval_rows"]} test cases' if real
                 else f'Synthetic complaints with planted problems, {h["eval_rows"]} test cases')
    run_note = (f'{h["bronze_rows"]:,} complaints from a Databricks lakehouse' if real else 'Generated data, not real complaints')
    banner = "" if real else '<div class="banner"><strong>Synthetic data.</strong> Not real complaints.</div>'
    links = []
    if video_url:
        links.append(f'<a class="primary" href="{_e(video_url)}">Watch the 60-second demo</a>')
    links.append(f'<a href="{REPO_URL}">GitHub</a>')
    if has_real:
        links.append('<a href="real/">Real data report</a>')
    if has_synthetic:
        links.append('<a href="synthetic/">Synthetic report</a>')
    if has_env:
        links.append('<a href="env/">RL environment</a>')
    leak, rest = h.get("naive_v1_on_leaked"), h.get("naive_v1_on_clean")
    leak_note = (f"Agent got {_frac(leak)} of these right, vs {_pct(rest)} of the rest." if leak and rest
                 else "These have a copy in the corpus the agent searches.")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eval QC Harness</title>
<meta name="description" content="A QC gate for eval datasets. It catches leaked, duplicated, or broken test cases before they lie to your scorer.">
<style>{CSS}{LANDING_CSS}</style></head>
<body>
<header class="topbar hero"><div class="inner"><div class="row"><div>
<div class="eyebrow">Eval QC harness</div>
<h1>A QC gate for eval datasets</h1>
<p class="lede">It catches leaked, duplicated, or broken test cases before they lie to your scorer.</p></div>
<button class="theme" id="theme" type="button">Dark theme</button></div>
<nav class="links">{"".join(links)}</nav>
</div></header>
<main class="wrap">
{banner}
<div class="run-label"><h2>{_e(run_title)}</h2><span class="muted">{_e(run_note)}</span></div>
<div class="big3">
<div class="tile crit"><div class="label">Blocked before scoring</div>
<div class="value">{h["blocked_rows"]:,} <small>of {h["bronze_rows"]:,} raw rows</small></div>
<div class="note">{_e(_step_note(h))}</div></div>
<div class="tile crit"><div class="label">Leaked in a random split</div>
<div class="value">{h["naive_leaked_cases"]} <small>of {h["naive_eval_rows"]} test cases</small></div>
<div class="note">{leak_note}</div></div>
<div class="tile good"><div class="label">Agent on the clean test set</div>
<ul class="rates">
<li><span>Faithful quote</span><b>{_pct(a["faithful_quote"])}</b></li>
<li><span>Right escalation call</span><b>{_pct(a["escalation_decision"])}</b></li>
<li><span>Required escalations made</span><b>{_pct(a["guardrail"])}</b></li>
</ul></div>
</div>
{_example(h)}
<div class="grid2">
<section class="card"><h3>Try it</h3>
<pre class="try">git clone {REPO_URL}
cd eval-qc-harness
python run.py --dataset cfpb-200</pre>
<p class="how" style="margin-top:8px">Python 3.10+, no installs.</p></section>
<section class="card"><h3>What the gate checks</h3>
<ul class="plain">
<li>Row counts add up</li>
<li>No duplicates</li>
<li>No test cases leaked into the corpus</li>
<li>Corpus older than the test set</li>
<li>Enough cases per label</li>
</ul></section>
</div>
<footer><a href="{REPO_URL}">Source on GitHub</a></footer>
</main><script>{JS}</script></body></html>"""


README_START = "<!-- results:start -->"
README_END = "<!-- results:end -->"


def readme_block(h):
    a = h["agent"]
    leak, rest = h.get("naive_v1_on_leaked"), h.get("naive_v1_on_clean")
    links = [f"[Live dashboard]({config.SITE_URL})"]
    if config.DEMO_VIDEO_URL:
        links.insert(0, f"[60-second demo]({config.DEMO_VIDEO_URL})")
    if h["dataset"] == "real":
        head = f"On real CFPB complaints ({h['eval_rows']} test cases), the gate"
    else:
        head = f"The real CFPB run is pending. On synthetic data with planted problems ({h['eval_rows']} test cases), the gate"
    clean = "passes all of them" if h["gate_clean"] == "PASS" else f"fails {h['checks_failed_clean']}"
    leak_line = (f"The agent got {_frac(leak)} leaked cases right ({_pct(leak)}) and {_pct(rest)} of the rest. "
                 if leak and rest else "")
    return "\n".join([
        README_START,
        f"{head} blocked {h['blocked_rows']:,} of {h['bronze_rows']:,} raw rows before scoring "
        f"({_step_note(h)}) and kept {h['eval_pool_near_copies_removed']} near copies out of the test set. "
        f"A naive random split of the same rows leaks {h['naive_leaked_cases']} of {h['naive_eval_rows']} test cases "
        f"into the search corpus and fails {h['checks_failed_naive']} of {h['checks_total']} checks; the clean split {clean}. "
        f"{leak_line}"
        f"On the clean set, the agent's quotes are faithful {_pct(a['faithful_quote'])} of the time, its escalate-or-not "
        f"decision is right {_pct(a['escalation_decision'])}, and it makes {_pct(a['guardrail'])} of required escalations.",
        "",
        " · ".join(links),
        README_END,
    ])


def update_readme(path, h):
    text = path.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        return False
    before, rest = text.split(README_START, 1)
    after = rest.split(README_END, 1)[1]
    path.write_text(before + readme_block(h) + after, encoding="utf-8")
    return True
