import random
import sqlite3

from .core import ToolError

NAME = "dataqc"
OUTCOMES = ("unique", "not_null", "positive", "not_after", "allowed", "references")
LOAD_DATE = "2026-06-30"
CURRENCIES = ("USD", "EUR", "GBP")
CUSTOMERS = tuple(f"C-{n}" for n in range(1, 9))
ROWS = 24
MAX_RESULT_ROWS = 100

RULES = {
    "unique": {"rule": "unique", "column": "payment_id"},
    "not_null": {"rule": "not_null", "column": "customer_id"},
    "positive": {"rule": "positive", "column": "amount"},
    "not_after": {"rule": "not_after", "column": "paid_at", "value": LOAD_DATE},
    "allowed": {"rule": "allowed", "column": "currency", "values": list(CURRENCIES)},
    "references": {"rule": "references", "column": "customer_id", "table": "customers", "ref_column": "customer_id"},
}

PLANS = [("unique", "not_null"), ("positive", "not_after"), ("allowed", "references"), ("unique", "positive"),
         ("not_null", "allowed"), ("not_after", "references"), ("unique", "references"), ("not_null", "positive"),
         ("not_after", "allowed"), ("references", "positive")]

TOOLS = {
    "describe": "Return the table schemas and row counts.",
    "run_sql": "args: query. Run one read-only SQL query and return up to 100 rows.",
    "flag": "args: row_ids (list of ints). Flag rows that break a rule.",
}


def _base_rows(rng):
    rows = []
    for k in range(ROWS):
        rows.append({"row_id": k + 1, "payment_id": 1000 + k, "customer_id": rng.choice(CUSTOMERS),
                     "amount": round(rng.uniform(5, 500), 2),
                     "paid_at": f"2026-{rng.choice(['05', '06'])}-{rng.randint(1, 28):02d}",
                     "currency": rng.choice(CURRENCIES)})
    return rows


def _plant(rule, rows, rng, used):
    free = [r for r in rows if r["row_id"] not in used]
    target = rng.choice(free)
    if rule == "unique":
        other = rng.choice([r for r in free if r is not target])
        target["payment_id"] = other["payment_id"]
        return [target["row_id"], other["row_id"]]
    if rule == "not_null":
        target["customer_id"] = None
    elif rule == "positive":
        target["amount"] = rng.choice([0.0, -round(rng.uniform(5, 200), 2)])
    elif rule == "not_after":
        target["paid_at"] = f"2026-07-{rng.randint(1, 9):02d}"
    elif rule == "allowed":
        target["currency"] = rng.choice(["usd", "JPY", "CAD"])
    elif rule == "references":
        target["customer_id"] = rng.choice(["C-42", "C-99", "C-0"])
    return [target["row_id"]]


def _make_task(task_id, seed, plan, reward_mode="exact"):
    rng = random.Random(seed)
    rows = _base_rows(rng)
    extra = rng.sample([r for r in OUTCOMES if r not in plan], 2)
    active = sorted(set(plan) | set(extra), key=OUTCOMES.index)
    bad = set()
    for rule in plan:
        for _ in range(rng.randint(1, 2)):
            bad.update(_plant(rule, rows, rng, bad))
    return {
        "id": task_id, "family": NAME,
        "prompt": (f"Table payments was loaded on {LOAD_DATE}. Check it against the rules in the spec and flag "
                   "every row that breaks at least one rule, using row_id. For a unique rule, flag every row that "
                   "shares the duplicated value."),
        "spec": {"table": "payments", "rules": [RULES[r] for r in active]},
        "data": {"payments": rows, "customers": list(CUSTOMERS)},
        "hidden": {"bad_rows": sorted(bad), "violated": list(plan)},
        "reward_mode": reward_mode,
    }


def make_tasks(dirty=False, seed=7):
    tasks = [_make_task(f"dataqc-{i + 1:02d}", seed * 100 + i, plan) for i, plan in enumerate(PLANS)]
    if dirty:
        tasks.append(_make_task("dataqc-dirty-lenient", seed * 100 + 77, ("positive", "allowed"),
                                reward_mode="contains"))
    return tasks


def initial_state(task):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE payments (row_id INTEGER PRIMARY KEY, payment_id INTEGER, customer_id TEXT, "
                 "amount REAL, paid_at TEXT, currency TEXT)")
    conn.execute("CREATE TABLE customers (customer_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO payments VALUES (:row_id, :payment_id, :customer_id, :amount, :paid_at, :currency)",
                     task["data"]["payments"])
    conn.executemany("INSERT INTO customers VALUES (?)", [(c,) for c in task["data"]["customers"]])
    conn.commit()
    conn.execute("PRAGMA query_only = ON")
    return {"conn": conn, "flagged": set(), "row_ids": {r["row_id"] for r in task["data"]["payments"]}}


def apply(state, tool, args):
    conn = state["conn"]
    if tool == "describe":
        tables = {}
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({name})")]
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            tables[name] = {"columns": cols, "rows": count}
        return tables
    if tool == "run_sql":
        query = str(args.get("query", ""))
        try:
            cur = conn.execute(query)
        except sqlite3.Error as e:
            raise ToolError(f"sql error: {e}")
        cols = [d[0] for d in cur.description] if cur.description else []
        return {"columns": cols, "rows": [list(r) for r in cur.fetchmany(MAX_RESULT_ROWS)]}
    if tool == "flag":
        ids = args.get("row_ids")
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise ToolError("row_ids must be a list of ints")
        unknown = [i for i in ids if i not in state["row_ids"]]
        if unknown:
            raise ToolError(f"unknown row_ids {unknown}")
        state["flagged"].update(ids)
        return f"{len(state['flagged'])} rows flagged"
    raise ToolError(f"unhandled tool {tool}")


def final_answer(state):
    return {"flagged": sorted(state["flagged"])}


def reward(task, state):
    bad = set(task["hidden"]["bad_rows"])
    if task.get("reward_mode") == "contains":
        return int(bad <= state["flagged"])
    return int(state["flagged"] == bad)


def close(state):
    state["conn"].close()


def outcome(task):
    return list(task["hidden"]["violated"])


def leak_strings(task):
    return [f"{word} {r}" for r in task["hidden"]["bad_rows"] for word in ("row", "row_id", "rows")]


def rule_sql(rule, table):
    c = rule["column"]
    kind = rule["rule"]
    if kind == "unique":
        return f"SELECT row_id FROM {table} WHERE {c} IN (SELECT {c} FROM {table} GROUP BY {c} HAVING COUNT(*) > 1)"
    if kind == "not_null":
        return f"SELECT row_id FROM {table} WHERE {c} IS NULL"
    if kind == "positive":
        return f"SELECT row_id FROM {table} WHERE {c} <= 0"
    if kind == "not_after":
        return f"SELECT row_id FROM {table} WHERE {c} > '{rule['value']}'"
    if kind == "allowed":
        values = ", ".join(f"'{v}'" for v in rule["values"])
        return f"SELECT row_id FROM {table} WHERE {c} NOT IN ({values})"
    if kind == "references":
        return (f"SELECT row_id FROM {table} WHERE {c} IS NOT NULL AND {c} NOT IN "
                f"(SELECT {rule['ref_column']} FROM {rule['table']})")
    raise ValueError(kind)


def oracle(task):
    bad = task["hidden"]["bad_rows"]

    def agent(start):
        yield {"tool": "flag", "args": {"row_ids": list(bad)}}
        yield {"tool": "submit"}
    return agent


def _check_rules(start, kinds):
    table = start["spec"]["table"]
    found = set()
    for rule in start["spec"]["rules"]:
        if rule["rule"] not in kinds:
            continue
        obs = yield {"tool": "run_sql", "args": {"query": rule_sql(rule, table)}}
        if obs["ok"]:
            found.update(r[0] for r in obs["result"]["rows"])
    if found:
        yield {"tool": "flag", "args": {"row_ids": sorted(found)}}
    yield {"tool": "submit"}


def v1_nulls_and_dupes(start):
    yield from _check_rules(start, {"not_null", "unique"})


def v2_all_rules(start):
    yield from _check_rules(start, set(OUTCOMES))


def flag_all(start):
    obs = yield {"tool": "run_sql", "args": {"query": f"SELECT row_id FROM {start['spec']['table']}"}}
    yield {"tool": "flag", "args": {"row_ids": [r[0] for r in obs["result"]["rows"]]}}
    yield {"tool": "submit"}


def flag_last_rows(start):
    obs = yield {"tool": "run_sql", "args": {"query": f"SELECT MAX(row_id) FROM {start['spec']['table']}"}}
    top = obs["result"]["rows"][0][0]
    yield {"tool": "flag", "args": {"row_ids": [top - 2, top - 1, top]}}
    yield {"tool": "submit"}


AGENTS = {"v1": v1_nulls_and_dupes, "v2": v2_all_rules}
SHORTCUTS = {"flag_all": flag_all, "flag_last_rows": flag_last_rows}
