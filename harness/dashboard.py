import math
from collections import Counter, defaultdict
from html import escape

from . import config

PAGES = [("data", "Test data"), ("agent", "Agent"), ("graders", "Code graders"), ("judge", "LLM judge")]
METRICS = [
    ("product_match", "Product correct"),
    ("action_match", "Escalation decision correct"),
    ("guardrail", "Required escalations made"),
    ("faithful_bounded", "Quote passes strict check"),
]
SCORER_LABELS = {
    "product_match": "Product match",
    "action_match": "Escalation match",
    "guardrail": "Guardrail",
    "faithful_bounded": "Quote check, strict",
    "faithful_substring": "Quote check, plain",
}
SCORER_ORDER = ["product_match", "action_match", "guardrail", "faithful_bounded", "faithful_substring"]
PROBE_COLUMNS = [
    ("correct", "accepts a correct answer", "Correct answer"),
    ("mistake", "planted: wrong product", "Wrong product"),
    ("mistake", "planted: escalation flipped", "Flipped escalation"),
    ("mistake", "planted: one word changed in quote", "One word changed"),
    ("mistake", "planted: quote from another complaint", "Another complaint's quote"),
    ("shortcut", "shortcut: quote is the whole complaint", "Whole complaint"),
    ("shortcut", "shortcut: one-word quote", "One-word quote"),
    ("shortcut", "shortcut: quote is only redaction marks", "Redaction marks"),
    ("shortcut", "shortcut: empty quote", "Empty quote"),
    ("shortcut", "shortcut: always escalate", "Always escalate"),
    ("shortcut", "shortcut: always the most common product", "Most common product"),
]
KNOWN_BLIND_SPOTS = {
    ("faithful_substring", "shortcut: one-word quote"): "The plain quote check is kept only to show why the strict one exists.",
    ("faithful_substring", "shortcut: quote is the whole complaint"): "The plain quote check is kept only to show why the strict one exists.",
    ("guardrail", "shortcut: always escalate"): "The guardrail only checks required escalations. The over-escalation rate on the Agent page covers the rest.",
}
JUDGE_PROBES = [
    ("accepts a correct answer", "Passes a correct answer"),
    ("planted: wrong product", "Fails a wrong product"),
    ("planted: quote from another complaint", "Fails a quote from another complaint"),
    ("padding: wrong product + 'approved by a senior analyst'", "Fails a wrong product marked 'approved by a senior analyst'"),
    ("padding: wrong product + confident rationale", "Fails a wrong product with a confident explanation"),
]
SCORE_MEANING = {0: "Wrong product", 1: "Doubtful, or quote does not support it", 2: "Fits, quote is weak", 3: "Clearly fits"}

CSS = """
:root{color-scheme:light;
--page:#f4f4f1;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--border:rgba(11,11,11,.10);--clean:#2a78d6;--naive:#eb6834;--v2:#1baf7a;--judge:#6250d6;
--good:#0ca30c;--good-ink:#006300;--warn:#fab219;--warn-ink:#8a5a00;--crit:#d03b3b;--crit-ink:#b42828;
--good-tint:rgba(12,163,12,.13);--crit-tint:rgba(208,59,59,.13);
--top:#111214;--top-ink:#f0efec;--top-muted:#a9a8a1;--banner:#fff6e0}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--clean:#3987e5;--naive:#d95926;--v2:#199e70;--judge:#9085e9;
--good:#0ca30c;--good-ink:#0ca30c;--warn:#fab219;--warn-ink:#fab219;--crit:#d03b3b;--crit-ink:#e66767;
--good-tint:rgba(12,163,12,.20);--crit-tint:rgba(208,59,59,.22);
--top:#000;--top-ink:#f0efec;--top-muted:#a9a8a1;--banner:#2a2416}}
:root[data-theme="dark"]{color-scheme:dark;
--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--clean:#3987e5;--naive:#d95926;--v2:#199e70;--judge:#9085e9;
--good:#0ca30c;--good-ink:#0ca30c;--warn:#fab219;--warn-ink:#fab219;--crit:#d03b3b;--crit-ink:#e66767;
--good-tint:rgba(12,163,12,.20);--crit-tint:rgba(208,59,59,.22);
--top:#000;--top-ink:#f0efec;--top-muted:#a9a8a1;--banner:#2a2416}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.topbar{background:var(--top);color:var(--top-ink)}
.topbar .inner{max-width:1120px;margin:0 auto;padding:22px 16px 0}
.topbar .row{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--top-muted)}
.topbar h1{font-size:24px;font-weight:650;margin:2px 0 4px;letter-spacing:-.01em}
.topbar .meta{color:var(--top-muted);font-size:13px;margin:0}
button.theme{font:inherit;font-size:13px;background:transparent;color:var(--top-ink);border:1px solid rgba(255,255,255,.25);border-radius:6px;padding:6px 12px;cursor:pointer}
nav.tabs{display:flex;gap:4px;margin-top:18px;overflow-x:auto}
nav.tabs a{color:var(--top-muted);text-decoration:none;font-size:13px;padding:10px 14px;border-bottom:2px solid transparent;white-space:nowrap}
nav.tabs a:hover{color:var(--top-ink)}
nav.tabs a.active{color:var(--top-ink);border-bottom-color:var(--clean)}
nav.tabs a b{color:var(--top-ink);font-weight:600;margin-right:6px}
.wrap{max-width:1120px;margin:0 auto;padding:22px 16px 48px}
.banner{background:var(--banner);border:1px solid var(--border);border-left:4px solid var(--warn);border-radius:6px;padding:10px 14px;margin-bottom:18px}
h2{font-size:20px;font-weight:650;margin:0;letter-spacing:-.01em}
h3{font-size:14px;font-weight:600;margin:0 0 2px}
p{margin:0}
.sub{color:var(--ink-2)}
.muted{color:var(--muted)}
.verdicts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:26px}
@media (max-width:900px){.verdicts{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.verdicts{grid-template-columns:1fr}}
.verdict{background:var(--surface);border:1px solid var(--border);border-top:4px solid var(--muted);border-radius:8px;padding:12px 14px;text-decoration:none;color:inherit;display:block}
.verdict:hover{border-color:var(--axis)}
.verdict.current{box-shadow:0 0 0 2px var(--clean)}
.verdict.good{border-top-color:var(--good)}.verdict.warn{border-top-color:var(--warn)}.verdict.crit{border-top-color:var(--crit)}
.verdict .q{color:var(--ink-2);font-size:12px;margin-bottom:6px}
.verdict .big{font-size:18px;font-weight:650;line-height:1.25;margin:8px 0 4px}
.verdict .why{color:var(--ink-2);font-size:12px}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px;border:1px solid var(--border);white-space:nowrap}
.chip .ic{width:16px;height:16px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:10px;color:#fff;font-weight:700}
.chip.good{color:var(--good-ink)}.chip.good .ic{background:var(--good)}
.chip.warn{color:var(--warn-ink)}.chip.warn .ic{background:var(--warn);color:#0b0b0b}
.chip.crit{color:var(--crit-ink)}.chip.crit .ic{background:var(--crit)}
.chip.none{color:var(--ink-2)}.chip.none .ic{background:var(--muted)}
.page-head{display:flex;gap:14px;align-items:flex-start;margin-bottom:16px}
.num-badge{flex:none;width:32px;height:32px;border-radius:8px;background:var(--ink);color:var(--surface);display:flex;align-items:center;justify-content:center;font-weight:700}
.findings{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--clean);border-radius:6px;padding:12px 16px;margin-bottom:16px}
.findings.good{border-left-color:var(--good)}.findings.warn{border-left-color:var(--warn)}.findings.crit{border-left-color:var(--crit)}
.findings ul{margin:6px 0 0;padding-left:18px;color:var(--ink-2)}
.findings li{margin:3px 0}
.findings strong{color:var(--ink)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px 18px;margin-bottom:16px}
.card-title{margin-bottom:8px}
.how{color:var(--muted);font-size:12px;margin-top:2px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px;margin-bottom:16px}
.grid2>.card{margin-bottom:0}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}
@media (max-width:760px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px}
.tile .label{color:var(--ink-2);font-size:13px}
.tile .value{font-size:24px;font-weight:650;margin-top:2px}
.tile .note{color:var(--muted);font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 8px;padding:0;list-style:none;color:var(--ink-2);font-size:13px}
.legend li{display:flex;align-items:center;gap:6px}
.sw{width:10px;height:10px;border-radius:50%;display:inline-block;flex:none}
.chart{overflow-x:auto}
.chart svg{width:100%;min-width:540px;height:auto;display:block}
.chart text{fill:var(--ink-2);font-size:12px}
.chart text.ink{fill:var(--ink)}
.chart text.strong{fill:var(--ink);font-weight:600}
.chart .tick{fill:var(--muted);font-variant-numeric:tabular-nums}
details.tv{margin-top:8px}
details.tv summary{cursor:pointer;color:var(--ink-2);font-size:12px}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:4px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink-2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.total td{font-weight:600}
.pos{color:var(--good-ink);font-weight:600}.neg{color:var(--crit-ink);font-weight:600}
ul.checks{list-style:none;margin:8px 0 0;padding:0}
ul.checks li{display:grid;grid-template-columns:22px 1fr;gap:4px;padding:7px 0;border-top:1px solid var(--grid)}
ul.checks li:first-child{border-top:0}
.icon{font-weight:700;width:18px;height:18px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:11px;color:#fff;margin-top:2px}
.icon.ok{background:var(--good)}.icon.bad{background:var(--crit)}
.detail{color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.split-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
table.matrix{min-width:860px}
table.matrix th.col{writing-mode:vertical-rl;transform:rotate(180deg);text-align:left;white-space:nowrap;padding:8px 4px;height:150px;vertical-align:bottom}
table.matrix th.grp{text-align:center;color:var(--muted);font-weight:600;border-bottom:1px solid var(--grid)}
table.matrix td.cell{text-align:center;font-variant-numeric:tabular-nums;white-space:nowrap;padding:8px 4px;border-left:2px solid var(--surface)}
td.cell.ok{background:var(--good-tint)}td.cell.bad{background:var(--crit-tint);font-weight:600}td.cell.na{color:var(--muted)}
td.cell .mk{font-size:11px;margin-right:3px}
td.cell.ok .mk{color:var(--good-ink)}td.cell.bad .mk{color:var(--crit-ink)}
.notes{margin:10px 0 0;padding-left:18px;color:var(--ink-2);font-size:13px}
.cm{display:grid;grid-template-columns:auto 1fr 1fr;gap:4px;font-size:13px;max-width:440px}
.cm div{padding:10px;border-radius:6px;text-align:center}
.cm .h{color:var(--ink-2);font-weight:600;font-size:12px;padding:6px}
.cm .agree{background:var(--good-tint)}.cm .disagree{background:var(--crit-tint)}
.cm .n{font-size:22px;font-weight:650;display:block}
.empty{border:1px dashed var(--axis);border-radius:8px;padding:18px;color:var(--ink-2);background:var(--surface)}
code{font-family:ui-monospace,Consolas,monospace;font-size:12px;background:var(--page);border:1px solid var(--border);border-radius:4px;padding:1px 5px}
.pager{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:8px}
a.btn{border:1px solid var(--border);background:var(--surface);color:var(--ink);padding:9px 14px;border-radius:6px;text-decoration:none;font-weight:600;font-size:13px}
a.btn:hover{border-color:var(--axis)}
details.terms{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 16px;margin-top:24px}
details.terms summary{cursor:pointer;font-weight:600;font-size:13px;color:var(--ink-2)}
dl.glossary{display:grid;grid-template-columns:minmax(120px,180px) 1fr;gap:6px 16px;margin:12px 0 4px;font-size:13px}
dl.glossary dt{font-weight:600}dl.glossary dd{margin:0;color:var(--ink-2)}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.14);display:none;z-index:10;max-width:280px}
[data-tip]:focus{outline:2px solid var(--clean);outline-offset:2px}
footer{color:var(--muted);font-size:12px;margin-top:20px;border-top:1px solid var(--grid);padding-top:14px}
@media print{.topbar{background:#fff;color:#000}nav.tabs,button.theme,.pager{display:none}.page[hidden]{display:block!important}.card,.verdict,.tile{break-inside:avoid}}
"""

JS = """
(function(){
var root=document.documentElement,btn=document.getElementById('theme');
function current(){return root.dataset.theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')}
function label(){btn.textContent=current()==='dark'?'Light theme':'Dark theme'}
try{var saved=localStorage.getItem('evalqc-theme');if(saved)root.dataset.theme=saved}catch(e){}
label();
btn.addEventListener('click',function(){root.dataset.theme=current()==='dark'?'light':'dark';try{localStorage.setItem('evalqc-theme',root.dataset.theme)}catch(e){}label()});
var tip=document.getElementById('tip');
function show(el,x,y){tip.textContent=el.getAttribute('data-tip');tip.style.display='block';
var w=tip.offsetWidth,h=tip.offsetHeight;tip.style.left=Math.max(8,Math.min(x+12,innerWidth-w-8))+'px';tip.style.top=Math.max(8,y-h-10)+'px'}
document.querySelectorAll('[data-tip]').forEach(function(el){
el.addEventListener('mousemove',function(e){show(el,e.clientX,e.clientY)});
el.addEventListener('mouseleave',function(){tip.style.display='none'});
el.addEventListener('focus',function(){var r=el.getBoundingClientRect();show(el,r.left+r.width/2,r.top)});
el.addEventListener('blur',function(){tip.style.display='none'});});
var pages=['data','agent','graders','judge'];
function route(){var h=(location.hash||'#data').slice(1);if(pages.indexOf(h)<0)h='data';
document.querySelectorAll('.page').forEach(function(p){p.hidden=p.dataset.page!==h});
document.querySelectorAll('[data-tab]').forEach(function(a){var on=a.dataset.tab===h;a.classList.toggle('active',on);a.setAttribute('aria-selected',on)});
document.querySelectorAll('.verdict').forEach(function(v){v.classList.toggle('current',v.dataset.page===h)});}
window.addEventListener('hashchange',function(){route();window.scrollTo(0,0)});route();
})();
"""


def _e(x):
    return escape(str(x))


def _pct(x, digits=1):
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def _num(x):
    return f"{x:,}"


def _delta(a, b):
    if a is None or b is None:
        return "n/a"
    d = (b - a) * 100
    cls = "pos" if d > 0.05 else ("neg" if d < -0.05 else "")
    return f'<span class="{cls}">{d:+.1f}</span>'


def _chip(state, text):
    icon = {"good": "&#10003;", "warn": "!", "crit": "&#10005;", "none": "&ndash;"}[state]
    return f'<span class="chip {state}"><span class="ic">{icon}</span>{_e(text)}</span>'


def _table(headers, rows, num_cols=(), row_classes=None):
    head = "".join(f'<th class="{"num" if i in num_cols else ""}">{_e(h)}</th>' for i, h in enumerate(headers))
    body = []
    for k, r in enumerate(rows):
        cls = f' class="{row_classes[k]}"' if row_classes and row_classes[k] else ""
        body.append(f"<tr{cls}>" + "".join(f'<td class="{"num" if i in num_cols else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def _tv(headers, rows, num_cols=()):
    return f'<details class="tv"><summary>Show as table</summary>{_table(headers, rows, num_cols)}</details>'


def _card(title, how, body):
    return f'<div class="card"><div class="card-title"><h3>{_e(title)}</h3>' + (f'<p class="how">{how}</p>' if how else "") + f"</div>{body}</div>"


def _legend(items):
    return '<ul class="legend">' + "".join(
        f'<li><span class="sw" style="background:var({var})"></span>{_e(label)}</li>' for var, label in items) + "</ul>"


def _bar_path(x0, y, w, h, r=4):
    if w <= r:
        return f"M{x0:.1f} {y:.1f}h{max(w, 1):.1f}v{h:.1f}h{-max(w, 1):.1f}z"
    return (f"M{x0:.1f} {y:.1f}h{w - r:.1f}a{r} {r} 0 0 1 {r} {r}v{h - 2 * r:.1f}"
            f"a{r} {r} 0 0 1 {-r} {r}h{-(w - r):.1f}z")


def _short_step(step):
    s = step.split(" (")[0].replace("drop ", "").replace("Drop ", "")
    return s[0].upper() + s[1:]


def _short_product(p):
    return {"Credit reporting or other personal consumer reports": "Credit reporting",
            "Money transfer, virtual currency, or money service": "Money transfer",
            "Payday loan, title loan, personal loan, or advance loan": "Payday or personal loan"}.get(p, p)


def _axis_lo(values):
    low = min(values) if values else 0.0
    step = 0.05 if low >= 0.7 else (0.1 if low >= 0.4 else 0.2)
    return max(0.0, math.floor((low - 0.02) / step) * step)


def _tick_step(lo):
    span = 1 - lo
    return 0.05 if span <= 0.3 else (0.1 if span <= 0.6 else 0.2)


def _dumbbell(totals_clean, totals_naive, lo):
    width, label_w, right_w, row_h, top, axis_h = 760, 210, 80, 40, 6, 26
    plot_w = width - label_w - right_w
    height = top + row_h * len(METRICS) + axis_h

    def x(v):
        return label_w + plot_w * (v - lo) / (1 - lo)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Clean split versus naive split score">']
    step, t = _tick_step(lo), lo
    while t <= 1.0001:
        out.append(f'<line x1="{x(t):.1f}" y1="{top}" x2="{x(t):.1f}" y2="{top + row_h * len(METRICS)}" stroke="var(--grid)"/>')
        out.append(f'<text x="{x(t):.1f}" y="{height - 6}" text-anchor="middle" class="tick">{t * 100:.0f}%</text>')
        t += step
    for i, (m, label) in enumerate(METRICS):
        cy = top + i * row_h + row_h / 2
        c, n = totals_clean[m]["rate"], totals_naive[m]["rate"]
        out.append(f'<text x="{label_w - 10}" y="{cy + 4}" text-anchor="end" class="ink">{_e(label)}</text>')
        if c is None or n is None:
            continue
        same = abs(c - n) < 0.01
        out.append(f'<line x1="{x(c):.1f}" y1="{cy}" x2="{x(n):.1f}" y2="{cy}" stroke="var(--axis)" stroke-width="2" stroke-linecap="round"/>')
        for v, var, name, t_, dy in ((c, "--clean", "Clean split", totals_clean[m], -4 if same else 0),
                                     (n, "--naive", "Naive split", totals_naive[m], 4 if same else 0)):
            tip = f'{name}: {label} {_pct(v)} ({t_["passed"]}/{t_["n"]})'
            out.append(f'<circle cx="{x(v):.1f}" cy="{cy + dy}" r="5.5" fill="var({var})" stroke="var(--surface)" '
                       f'stroke-width="2" tabindex="0" data-tip="{_e(tip)}"/>')
        delta = (n - c) * 100
        out.append(f'<text x="{width - 4}" y="{cy + 4}" text-anchor="end" class="{"strong" if abs(delta) >= 1 else ""}">{delta:+.1f} pts</text>')
    out.append("</svg>")
    return "".join(out)


def _hbars(rows, var, label_w=260, target=None):
    width, bar_h, row_h, top, axis_h, right_w = 760, 14, 28, 4, 22, 70
    plot_w = width - label_w - right_w
    height = top + row_h * len(rows) + axis_h

    def x(v):
        return label_w + plot_w * v

    out = [f'<svg viewBox="0 0 {width} {height}" role="img">']
    for t in (0, .25, .5, .75, 1):
        out.append(f'<line x1="{x(t):.1f}" y1="{top}" x2="{x(t):.1f}" y2="{top + row_h * len(rows)}" stroke="var(--grid)"/>')
        out.append(f'<text x="{x(t):.1f}" y="{height - 6}" text-anchor="middle" class="tick">{t * 100:.0f}%</text>')
    if target is not None:
        out.append(f'<line x1="{x(target):.1f}" y1="{top}" x2="{x(target):.1f}" y2="{top + row_h * len(rows)}" stroke="var(--ink-2)"/>')
    for i, (label, value, tip) in enumerate(rows):
        y = top + i * row_h + (row_h - bar_h) / 2
        out.append(f'<text x="{label_w - 10}" y="{y + 11}" text-anchor="end" class="ink">{_e(label)}</text>')
        if value is None:
            continue
        out.append(f'<path d="{_bar_path(label_w, y, max(plot_w * value, 2), bar_h)}" fill="var({var})" tabindex="0" data-tip="{_e(tip)}"/>')
        out.append(f'<text x="{x(value) + 6:.1f}" y="{y + 11}" class="ink">{_pct(value)}</text>')
    out.append("</svg>")
    return "".join(out)


def _gate_card(title, desc, q):
    checks = q["checks"]
    passed = sum(1 for c in checks if c["status"] == "PASS")
    ok = q["gate"] == "PASS"
    items = "".join(
        f'<li><span class="icon {"ok" if c["status"] == "PASS" else "bad"}">{"&#10003;" if c["status"] == "PASS" else "&#10005;"}</span>'
        f'<div>{_e(c["check"][0].upper() + c["check"][1:])}<div class="detail">{_e(c["detail"])}</div></div></li>'
        for c in checks)
    return (f'<div class="card"><div class="split-head"><div><h3>{_e(title)}</h3><p class="how">{_e(desc)}</p></div>'
            f'{_chip("good" if ok else "crit", f"{passed} of {len(checks)} passed")}</div>'
            f'<ul class="checks">{items}</ul></div>')


def _grader_matrix(table):
    cells = {(r["scorer"], r["probe"]): r for r in table}
    scorers = [s for s in SCORER_ORDER if any(k[0] == s for k in cells)]
    groups = [("Correct", 1), ("Planted mistakes", 4), ("Shortcuts", 6)]
    head1 = "<tr><th></th>" + "".join(f'<th class="grp" colspan="{n}">{_e(g)}</th>' for g, n in groups) + "</tr>"
    head2 = "<tr><th>Scorer</th>" + "".join(f'<th class="col">{_e(lab)}</th>' for _, _, lab in PROBE_COLUMNS) + "</tr>"
    body = []
    for s in scorers:
        row = [f"<td><strong>{_e(SCORER_LABELS.get(s, s))}</strong></td>"]
        for kind, probe, lab in PROBE_COLUMNS:
            r = cells.get((s, probe))
            if r is None:
                row.append('<td class="cell na" title="Not applicable">&middot;</td>')
                continue
            good_n = r["passed"] if kind == "correct" else r["caught"]
            verb = "accepted" if kind == "correct" else "caught"
            note = KNOWN_BLIND_SPOTS.get((s, probe), "")
            tip = f'{SCORER_LABELS.get(s, s)}, {lab}: {verb} {good_n} of {r["n"]}' + (f". {note}" if note else "")
            row.append(f'<td class="cell {"ok" if r["good"] else "bad"}" tabindex="0" data-tip="{_e(tip)}">'
                       f'<span class="mk">{"&#10003;" if r["good"] else "&#10005;"}</span>{good_n / r["n"] * 100:.0f}%</td>')
        body.append("<tr>" + "".join(row) + "</tr>")
    return f'<div class="table-wrap"><table class="matrix"><thead>{head1}{head2}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _verdicts(results):
    qc, runs, judge = results["qc"], results["runs"], results.get("judge") or {}
    out = []
    gate_ok = qc["time"]["gate"] == "PASS"
    naive_fail = sum(1 for c in qc["naive"]["checks"] if c["status"] == "FAIL")
    out.append(("data", "good" if gate_ok else "crit", "Trusted" if gate_ok else "Not trusted",
                "Can we trust the test data?", "Yes, the clean split" if gate_ok else "No, fix the data first",
                f'Clean split passed all {len(qc["time"]["checks"])} checks. The naive split failed {naive_fail}.'
                if gate_ok else "The clean split failed a check, so the scores are not reliable."))
    v2 = runs[("time", "v2_vote")]["totals"]
    reg = results["regression"]
    broken = sum(r["broken"] for r in reg.values())
    out.append(("agent", "good" if broken == 0 else "warn", "No regressions" if broken == 0 else "Regressions found",
                "How good is the agent?", f'{_pct(v2["product_match"]["rate"], 1)} of products right',
                f'v2 fixed {reg["product_match"]["fixed"]} product mistakes and broke {reg["product_match"]["broken"]}.'))
    unexpected = [r for r in results["gradercheck"] if not r["good"] and (r["scorer"], r["probe"]) not in KNOWN_BLIND_SPOTS]
    known = [r for r in results["gradercheck"] if not r["good"] and (r["scorer"], r["probe"]) in KNOWN_BLIND_SPOTS]
    out.append(("graders", "crit" if unexpected else ("warn" if known else "good"),
                "New blind spot" if unexpected else ("Known gaps" if known else "Trusted"),
                "Can the code graders be cheated?",
                f"{len(unexpected)} new blind spots" if unexpected else ("Only in known places" if known else "No"),
                f"{len(known)} known gaps, each documented." if not unexpected else "A scorer missed a planted mistake."))
    if judge.get("status") == "ran":
        probes = {p["probe"]: p for p in judge["probes"]}
        wrong = probes.get("planted: wrong product", {"rate": None, "good": 0, "n": 0})
        cons = judge["consistency"]["rate"] or 0
        rate = wrong["rate"] if wrong["rate"] is not None else 1
        state = "crit" if rate < 0.9 else ("warn" if cons < 0.9 else "good")
        out.append(("judge", state, {"crit": "Not trusted alone", "warn": "Use with care", "good": "Trusted"}[state],
                    "Can we trust the LLM judge?",
                    f'Missed {wrong["n"] - wrong["good"]} of {wrong["n"]} wrong answers' if rate < 1 else "Caught every wrong answer",
                    f"Same score on repeat runs for {_pct(cons, 0)} of answers."))
    else:
        out.append(("judge", "none", "Not run", "Can we trust the LLM judge?", "Not run yet", "Add an API key and run with --judge."))
    return out


def _findings(state, items):
    return f'<div class="findings {state}"><strong>Key findings</strong><ul>{"".join(f"<li>{i}</li>" for i in items)}</ul></div>'


def _page_head(num, title, sub):
    return (f'<div class="page-head"><span class="num-badge">{num}</span><div><h2>{_e(title)}</h2>'
            f'<p class="sub">{_e(sub)}</p></div></div>')


def _pager(idx):
    prev = f'<a class="btn" href="#{PAGES[idx - 1][0]}">&larr; {_e(PAGES[idx - 1][1])}</a>' if idx > 0 else "<span></span>"
    nxt = f'<a class="btn" href="#{PAGES[idx + 1][0]}">{_e(PAGES[idx + 1][1])} &rarr;</a>' if idx < len(PAGES) - 1 else "<span></span>"
    return f'<div class="pager">{prev}{nxt}</div>'


def _data_page(results, state, t_clean, t_naive, lo):
    qc, splits, manifest = results["qc"], results["splits"], results["silver_manifest"]
    steps = manifest["steps"]
    eval_rows = (results.get("eval_rows") or {}).get("time", [])
    infl = (t_naive["v1_nearest"]["product_match"]["rate"] - t_clean["v1_nearest"]["product_match"]["rate"]) * 100
    fails = sum(1 for c in qc["naive"]["checks"] if c["status"] == "FAIL")
    items = [
        f'<strong>{_num(steps[-1]["rows"])} of {_num(steps[0]["rows"])} rows</strong> survived cleaning, and every removed row is accounted for.',
        f'<strong>{splits["time"].get("eval_pool_near_duplicates_removed", 0)} near copies</strong> of older complaints were pulled out of the test set before scoring.',
        f'The naive split failed <strong>{fails} of {len(qc["naive"]["checks"])}</strong> checks, including leakage, so the QC gate would block it.',
        f'On the naive split, v1 looks <strong>{infl:+.1f} points</strong> better at picking the product. That gap is leakage, not skill.',
    ]
    lineage_rows = [[_e(_short_step(s["step"])), _num(s["dropped"]) if s["dropped"] else "-", _num(s["rows"])] for s in steps]
    lineage = _card("How the data was cleaned",
                    f'Raw rows minus every removal equals the rows kept: {"reconciled" if manifest["reconciled"] else "<strong>not reconciled</strong>"}.',
                    _table(["Step", "Rows removed", "Rows left"], lineage_rows, (1, 2),
                           [""] * (len(steps) - 1) + ["total"]))
    mix = ""
    if eval_rows:
        total = len(eval_rows)
        prod = Counter(_short_product(r["product"]) for r in eval_rows).most_common()
        rules = Counter()
        for r in eval_rows:
            hits = r.get("rules") or []
            key = ("No escalation needed" if not hits else "Both rules" if len(hits) > 1
                   else "Fraud or identity theft" if hits[0] == "fraud_or_identity_theft" else "Servicemember or older consumer")
            rules[key] += 1
        order = ["No escalation needed", "Fraud or identity theft", "Servicemember or older consumer", "Both rules"]
        p_tab = _table(["Product", "Cases", "Share"], [[_e(k), _num(v), _pct(v / total, 0)] for k, v in prod], (1, 2))
        r_tab = _table(["Escalation rule", "Cases", "Share"], [[_e(k), _num(rules.get(k, 0)), _pct(rules.get(k, 0) / total, 0)] for k in order], (1, 2))
        mix = _card("What is in the test set", f"{total} test complaints, newer than everything in the retrieval corpus.",
                    f'<div class="grid2" style="margin:0">{p_tab}{r_tab}</div>')
    gates = (f'<div class="grid2">{_gate_card("Clean split", "Corpus older than the test set, duplicates and near copies removed", qc["time"])}'
             f'{_gate_card("Naive split", "Random split on raw rows, no cleaning. Built to show what goes wrong.", qc["naive"])}</div>')
    leak_tv = [[_e(f'{a.split("_")[0]}: {label}'), _pct(t_clean[a][m]["rate"]), _pct(t_naive[a][m]["rate"]),
                _delta(t_clean[a][m]["rate"], t_naive[a][m]["rate"])]
               for a in ("v1_nearest", "v2_vote") for m, label in METRICS]
    leak = _card("What leakage does to the score",
                 "Same agent, same data, two ways of splitting it. The number on the right is how much the naive split inflates the score.",
                 _legend([("--clean", "Clean split"), ("--naive", "Naive split")])
                 + '<p class="sub" style="font-weight:600;margin:4px 0">v1 nearest</p>'
                 + f'<div class="chart">{_dumbbell(t_clean["v1_nearest"], t_naive["v1_nearest"], lo)}</div>'
                 + '<p class="sub" style="font-weight:600;margin:14px 0 4px">v2 vote</p>'
                 + f'<div class="chart">{_dumbbell(t_clean["v2_vote"], t_naive["v2_vote"], lo)}</div>'
                 + _tv(["Metric", "Clean", "Naive", "Inflation (pts)"], leak_tv, (1, 2, 3)))
    return (_page_head(1, "Can we trust the test data?", "Before any score counts, the test set has to be clean, leak-free and newer than the corpus.")
            + _findings(state, items) + leak + gates + lineage + mix)


def _agent_page(results, state, t_clean):
    runs, reg = results["runs"], results["regression"]
    eval_rows = (results.get("eval_rows") or {}).get("time", [])
    v1, v2 = t_clean["v1_nearest"], t_clean["v2_vote"]
    score_rows = [[_e(label), _pct(v1[m]["rate"]), _pct(v2[m]["rate"]), _delta(v1[m]["rate"], v2[m]["rate"])] for m, label in METRICS]
    score_rows.append(["Escalated when not needed <span class=\"muted\">(lower is better)</span>",
                       _pct(v1["over_escalation"]["rate"]), _pct(v2["over_escalation"]["rate"]),
                       _delta(v2["over_escalation"]["rate"], v1["over_escalation"]["rate"])])
    scores = _card("Scores on the clean split", f'{v2["product_match"]["n"]} test complaints. Change is v2 minus v1, in percentage points.',
                   _table(["Metric", "v1 nearest", "v2 vote", "Change"], score_rows, (1, 2, 3)))
    reg_rows = [[_e(label), _num(reg[m]["fixed"]), _num(reg[m]["broken"]), _e(", ".join(reg[m]["broken_examples"]) or "-")]
                for m, label in METRICS]
    regression = _card("What v2 fixed and broke", "Fixed: v1 wrong, v2 right. Broken: v1 right, v2 wrong. Averages can hide these trade-offs.",
                       _table(["Metric", "Fixed", "Broken", "Broken examples"], reg_rows, (1, 2)))
    esc = ""
    product = ""
    confusion = ""
    worst = None
    if eval_rows:
        need = {r["complaint_id"]: r["expected_escalate"] for r in eval_rows}
        names = [("caught", "Escalated when required"), ("missed", "Missed a required escalation"),
                 ("over", "Escalated when not needed"), ("quiet", "Correctly left alone")]
        counts = {}
        for agent in ("v1_nearest", "v2_vote"):
            c = {k: 0 for k, _ in names}
            for o in runs[("time", agent)]["outputs"]:
                req, did = need.get(o["complaint_id"]), bool(o.get("escalate"))
                if req is None:
                    continue
                c["caught" if req and did else "missed" if req else "over" if did else "quiet"] += 1
            counts[agent] = c
        esc = _card("Escalation outcomes", "Counts across the test set. Missing a required escalation is the costly mistake.",
                    _table(["Outcome", "v1", "v2"], [[_e(l), _num(counts["v1_nearest"][k]), _num(counts["v2_vote"][k])] for k, l in names], (1, 2)))
        by_id = {r["complaint_id"]: r["product"] for r in eval_rows}
        stats = defaultdict(lambda: [0, 0])
        for p in runs[("time", "v2_vote")]["per_case"]:
            prod = by_id.get(p["complaint_id"])
            if prod:
                stats[prod][1] += 1
                stats[prod][0] += bool(p["product_match"])
        prod_rows = sorted(((k, v[0] / v[1], v[0], v[1]) for k, v in stats.items() if v[1]), key=lambda r: r[1])
        worst = prod_rows[0] if prod_rows else None
        product = _card("v2 accuracy by product", "Sorted from weakest to strongest. The overall score hides where the agent struggles.",
                        f'<div class="chart">{_hbars([(_short_product(p), r, f"{_short_product(p)}: {c} of {n} right") for p, r, c, n in prod_rows], "--v2", label_w=220)}</div>'
                        + _tv(["Product", "Right", "Cases", "Accuracy"], [[_e(p), _num(c), _num(n), _pct(r)] for p, r, c, n in prod_rows], (1, 2, 3)))
        pairs = Counter((_short_product(by_id[o["complaint_id"]]), _short_product(o["product"] or "none"))
                        for o in runs[("time", "v2_vote")]["outputs"]
                        if o["complaint_id"] in by_id and o["product"] != by_id[o["complaint_id"]]).most_common(6)
        confusion = _card("Products v2 mixes up", "The most common wrong answers. Repeated pairs point to product labels that overlap.",
                          _table(["Real product", "v2 said", "Cases"], [[_e(a), _e(b), _num(n)] for (a, b), n in pairs], (2,))
                          if pairs else '<p class="muted">v2 got every product right.</p>')
    items = [
        f'v2 gets <strong>{_pct(v2["product_match"]["rate"])}</strong> of products right, up from {_pct(v1["product_match"]["rate"])} for v1.',
        f'v2 fixed <strong>{reg["product_match"]["fixed"]}</strong> product mistakes and <strong>{reg["action_match"]["fixed"]}</strong> escalation mistakes, '
        f'and broke <strong>{reg["product_match"]["broken"] + reg["action_match"]["broken"]}</strong> cases that v1 had right.',
        f'It escalated {_pct(v2["over_escalation"]["rate"], 0)} of complaints that did not need it, so its perfect guardrail score is not from escalating everything.',
    ]
    if worst:
        items.append(f'Weakest product: <strong>{_e(_short_product(worst[0]))}</strong>, {worst[2]} of {worst[3]} right.')
    return (_page_head(2, "How good is the agent?", "Scored on the clean split only. v1 is the old version, v2 the new one.")
            + _findings(state, items) + scores + f'<div class="grid2">{regression}{esc}</div>' + product + confusion)


def _graders_page(results, state):
    table = results["gradercheck"]
    blind = [r for r in table if not r["good"]]
    unexpected = [r for r in blind if (r["scorer"], r["probe"]) not in KNOWN_BLIND_SPOTS]
    total_tests = len(table)
    items = [
        f"{total_tests} tests across {len({r['scorer'] for r in table})} scorers: correct answers they should accept, planted mistakes and cheating answers they should reject.",
        f"<strong>{len(unexpected)}</strong> unexpected blind spots." if unexpected
        else "The scorers behind the agent's score caught every planted mistake and every cheating answer they apply to.",
        f"<strong>{len(blind) - len(unexpected)}</strong> known gaps, listed under the matrix with the reason each one is acceptable.",
    ]
    notes = sorted({f'{SCORER_LABELS.get(r["scorer"])}: {KNOWN_BLIND_SPOTS[(r["scorer"], r["probe"])]}' for r in blind
                    if (r["scorer"], r["probe"]) in KNOWN_BLIND_SPOTS})
    matrix = _card("Grader test matrix",
                   "Rows are scorers, columns are tests. Green means the scorer did the right thing every time, red means it was fooled at least once, and a dot means the test does not apply. Hover a cell for counts.",
                   _grader_matrix(table) + (f'<ul class="notes">{"".join(f"<li>{_e(n)}</li>" for n in notes)}</ul>' if notes else ""))
    return (_page_head(3, "Can the code graders be cheated?", "A score is only as good as the grader, so each one is tested before its numbers are used.")
            + _findings(state, items) + matrix)


def _judge_page(judge, state):
    head = _page_head(4, "Can we trust the LLM judge?", "An LLM rates each answer 0 to 3. Its evidence must be copied word for word from the complaint, or code caps the score at 1.")
    if judge.get("status") != "ran":
        return head + (f'<div class="empty"><strong>The LLM judge has not run.</strong> {_e(judge.get("message", ""))}'
                       f'<br><span class="muted">Then run <code>python -m harness all --judge</code>. Answers are saved, so reruns cost nothing.</span></div>')
    probes = {p["probe"]: p for p in judge["probes"]}
    wrong = probes.get("planted: wrong product", {"good": 0, "n": 0})
    cons, grd = judge["consistency"], judge["grounding"]
    pers = judge.get("persuasion", {"flips": 0, "chances": 0})
    items = [
        f'{_e(judge["model"])} passed <strong>{wrong["n"] - wrong["good"]} of {wrong["n"]}</strong> answers with a deliberately wrong product.',
        f'Adding "approved by a senior analyst" or a confident explanation flipped <strong>{pers["flips"]} of {pers["chances"]}</strong> verdicts it had gotten right.',
        f'It gave the same score on {cons["repeats"]} repeat runs for {_pct(cons["rate"], 0)} of answers.',
        "Use it as a second opinion next to the code checks, not as the only grader." if state == "crit" else "It held up on these tests.",
    ]
    tiles = '<div class="tiles">' + "".join([
        f'<div class="tile"><div class="label">Wrong products caught</div><div class="value">{wrong["good"]} of {wrong["n"]}</div><div class="note">should be all of them</div></div>',
        f'<div class="tile"><div class="label">Same score on every repeat</div><div class="value">{_pct(cons["rate"], 0)}</div><div class="note">{cons["identical_scores"]} of {cons["cases"]} answers</div></div>',
        f'<div class="tile"><div class="label">Swayed by persuasion</div><div class="value">{pers["flips"]} of {pers["chances"]}</div><div class="note">verdicts flipped</div></div>',
        f'<div class="tile"><div class="label">Evidence copied word for word</div><div class="value">{_pct(grd["grounded"] / grd["verdicts"] if grd["verdicts"] else None, 0)}</div><div class="note">{grd["capped_by_code"]} scores capped by code</div></div>',
    ]) + "</div>"
    bars, tv = [], []
    for key, label in JUDGE_PROBES:
        p = probes.get(key)
        if p and p["n"]:
            verb = "passed" if p["kind"] == "correct" else "failed"
            bars.append((label, p["rate"], f'{label}: {verb} {p["good"]} of {p["n"]}'))
            tv.append([_e(label), _num(p["good"]), _num(p["n"]), _pct(p["rate"], 0)])
    fooled = _card("Can the judge be fooled?", "How often the judge did the right thing on each test. Every bar should reach the line at 100%.",
                   f'<div class="chart">{_hbars(bars, "--judge", label_w=340, target=1.0)}</div>' + _tv(["Test", "Right", "Out of", "Rate"], tv, (1, 2, 3)))
    dist = judge.get("score_distribution", {})
    n_scored = judge["scored_cases"]
    dist_card = _card("How the judge scored the agent", f"{n_scored} agent answers. A useful judge spreads its scores across the scale.",
                      _table(["Score", "Meaning", "Answers", "Share"],
                             [[str(s), _e(SCORE_MEANING[s]), _num(dist.get(str(s), 0)), _pct(dist.get(str(s), 0) / n_scored if n_scored else None, 0)]
                              for s in range(4)], (2, 3)))
    cm = judge.get("confusion")
    kappa = judge.get("kappa_with_code_scorer")
    cm_card = ""
    if cm:
        note = ("Kappa is 0 because the judge passed every answer, so its high agreement says nothing about its judgment."
                if judge.get("judge_pass_rate") == 1.0 else
                f"Kappa {kappa:.2f} corrects agreement for chance. Above 0.6 is usually read as good." if kappa is not None else "")
        cm_card = _card("Judge versus the product label", f'Agreement {_pct(judge["agreement_with_code_scorer"], 0)}. {_e(note)}',
                        f'<div class="cm"><div></div><div class="h">Label says right</div><div class="h">Label says wrong</div>'
                        f'<div class="h">Judge passes</div><div class="agree"><span class="n">{cm["both_pass"]}</span>agree</div>'
                        f'<div class="disagree"><span class="n">{cm["judge_only"]}</span>judge too lenient?</div>'
                        f'<div class="h">Judge fails</div><div class="disagree"><span class="n">{cm["label_only"]}</span>judge too strict?</div>'
                        f'<div class="agree"><span class="n">{cm["both_fail"]}</span>agree</div></div>')
    ex = ""
    if judge.get("fooled_examples"):
        rows = [[_e(f["snippet"] + "..."), _e(_short_product(f["gold_product"])), _e(_short_product(f["wrong_product"])),
                 _e(f'{f["judge_score"]} of 3'), _e(f["reason"])] for f in judge["fooled_examples"]]
        ex = _card("Wrong answers the judge passed", "The planted product was wrong and the judge passed it anyway. Some of its reasons contradict its own score.",
                   _table(["Complaint starts", "Real product", "Planted product", "Judge", "Judge's reason"], rows))
    dis = ""
    if judge.get("disagreements"):
        rows = [[_e(d["complaint_id"]), _e(_short_product(d["gold_product"])), _e(_short_product(d["agent_product"])),
                 _e(f'{d["judge_score"]} of 3'), _e(d["reason"])] for d in judge["disagreements"]]
        dis = _card(f'Where the judge and the label disagree ({judge["disagreement_count"]})', "Read these by hand. Either the judge is wrong or the CFPB label is.",
                    _table(["Complaint", "Label", "Agent said", "Judge", "Judge's reason"], rows))
    return head + _findings(state, items) + tiles + fooled + f'<div class="grid2">{dist_card}{cm_card}</div>' + ex + dis


GLOSSARY = """
<details class="terms"><summary>Terms used in this report</summary><dl class="glossary">
<dt>Clean split</dt><dd>Older complaints form the retrieval corpus and newer ones form the test set, with duplicates and near copies removed.</dd>
<dt>Naive split</dt><dd>A random split of the raw rows. Test complaints can also sit in the corpus, so the agent can copy answers.</dd>
<dt>Leakage</dt><dd>When test cases, or near copies of them, are also in the data the agent searches. It makes scores look better than they are.</dd>
<dt>Planted mistake</dt><dd>A correct answer changed in one place, like a wrong product or one swapped word, to see if the grader notices.</dd>
<dt>Shortcut</dt><dd>A cheating answer, like quoting the whole complaint or escalating everything, that a weak grader would pass.</dd>
<dt>Regression</dt><dd>A case the old version got right and the new version gets wrong.</dd>
<dt>Kappa</dt><dd>Agreement between two graders after removing agreement expected by chance. 0 means no better than chance, 1 means perfect.</dd>
</dl></details>"""


def render(results):
    runs, sources = results["runs"], results["sources"]
    is_demo = any("NOT_REAL" in s["file"] for s in sources)
    judge = results.get("judge") or {"status": "skipped", "message": ""}
    verdicts = _verdicts(results)
    vstate = {v[0]: v[1] for v in verdicts}
    verdict_html = "".join(
        f'<a class="verdict {state}" href="#{anchor}" data-page="{anchor}"><div class="q">{_e(q)}</div>{_chip(state, chip)}'
        f'<div class="big">{_e(big)}</div><div class="why">{_e(why)}</div></a>'
        for anchor, state, chip, q, big, why in verdicts)
    t_clean = {a: runs[("time", a)]["totals"] for a in ("v1_nearest", "v2_vote")}
    t_naive = {a: runs[("naive", a)]["totals"] for a in ("v1_nearest", "v2_vote")}
    lo = _axis_lo([d[m]["rate"] for d in list(t_clean.values()) + list(t_naive.values())
                   for m, _ in METRICS if d[m]["rate"] is not None])
    bodies = {
        "data": _data_page(results, vstate["data"], t_clean, t_naive, lo),
        "agent": _agent_page(results, vstate["agent"], t_clean),
        "graders": _graders_page(results, vstate["graders"]),
        "judge": _judge_page(judge, vstate["judge"]),
    }
    pages_html = "".join(
        f'<section class="page" id="page-{key}" data-page="{key}"{"" if i == 0 else " hidden"}>{bodies[key]}{_pager(i)}</section>'
        for i, (key, _) in enumerate(PAGES))
    tabs = "".join(f'<a href="#{key}" data-tab="{key}" role="tab"><b>{i + 1}</b>{_e(label)}</a>' for i, (key, label) in enumerate(PAGES))
    banner = ('<div class="banner"><strong>Demo data.</strong> These complaints were generated to test the harness. '
              'They are not real, and the scores say nothing about real agent performance.</div>') if is_demo else ""
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eval QC Report</title><style>{CSS}</style></head>
<body>
<header class="topbar"><div class="inner"><div class="row"><div>
<div class="eyebrow">Eval QC harness</div><h1>Can this agent's score be trusted?</h1>
<p class="meta">Complaint-routing agent &middot; {_e(", ".join(s["file"] for s in sources))} &middot; generated {_e(results.get("generated_at", ""))}</p></div>
<button class="theme" id="theme" type="button">Dark theme</button></div>
<nav class="tabs" role="tablist">{tabs}</nav>
</div></header>
<main class="wrap">
{banner}
<div class="verdicts">{verdict_html}</div>
{pages_html}
{GLOSSARY}
<footer>Per-case traces in reports/traces &middot; all numbers in reports/results.json &middot; text version in reports/report.md</footer>
</main><div id="tip" role="tooltip"></div><script>{JS}</script></body></html>"""
    path = config.REPORTS / "dashboard.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
