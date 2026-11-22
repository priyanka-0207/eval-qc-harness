import copy
import re

from .core import ToolError

NAME = "tickets"
OUTCOMES = ("refund", "reply", "escalate")

POLICY = ("Refund the full order amount when an item arrives damaged and the customer reports it within 30 days "
          "of delivery. Do not refund after 30 days, reply to the customer instead. Escalate instead of refunding "
          "when the order amount is over $500 or the customer account is flagged for fraud review.")

TOOLS = {
    "get_policy": "Return the refund policy.",
    "get_customer": "args: customer_id. Return the customer record and account flags.",
    "list_orders": "args: customer_id. Return the customer's orders with item, amount and days since delivery.",
    "issue_refund": "args: order_id, amount. Refund an order.",
    "escalate": "args: reason. Hand the ticket to a human agent.",
    "reply": "args: message. Send a reply to the customer.",
}

CASES = [
    ("C-104", "espresso machine", 129.00, 4, False, "My espresso machine showed up with a cracked water tank. I want my money back."),
    ("C-118", "desk lamp", 48.50, 12, False, "The desk lamp I ordered came with a shattered shade. Can I get a refund?"),
    ("C-131", "rice cooker", 312.99, 30, False, "Opened the box today and the rice cooker lid is snapped off. Please refund it."),
    ("C-142", "yoga mat", 75.00, 1, False, "The yoga mat arrived torn down the middle. I'd like a refund."),
    ("C-157", "bluetooth speaker", 89.99, 45, False, "My bluetooth speaker stopped working and the casing is dented. Refund please."),
    ("C-163", "standing desk", 260.00, 31, False, "One leg of the standing desk was bent when it arrived. I want a refund."),
    ("C-170", "phone case", 19.99, 90, False, "The phone case I bought has a crack along the edge. Can you refund me?"),
    ("C-186", "road bike", 742.00, 3, False, "The road bike frame came scratched and the brake lever is broken. I need a refund."),
    ("C-192", "laptop", 1299.00, 20, False, "My new laptop has a dead pixel line and a dent on the lid. Refund it please."),
    ("C-205", "headphones", 64.00, 6, True, "The headphones arrived with one ear cup cracked. Please send my refund."),
]

DISTRACTORS = [("water bottle", 22.00, 15), ("notebook set", 14.75, 60), ("wall clock", 39.90, 8),
               ("garden hose", 31.25, 25), ("tea kettle", 54.00, 40)]


def _decision(amount, days, flagged):
    if flagged or amount > 500:
        return "escalate"
    if days <= 30:
        return "refund"
    return "reply"


def make_tasks(dirty=False):
    tasks = []
    for i, (cid, item, amount, days, flagged, text) in enumerate(CASES):
        n = int(cid.split("-")[1])
        target = f"O-{5000 + n * 7}"
        orders = [{"order_id": target, "item": item, "amount": amount, "days_since_delivery": days}]
        for j in range(2):
            d_item, d_amount, d_days = DISTRACTORS[(i + j) % len(DISTRACTORS)]
            orders.append({"order_id": f"O-{5000 + n * 7 + j + 1}", "item": d_item, "amount": d_amount,
                           "days_since_delivery": d_days})
        orders.sort(key=lambda o: o["order_id"], reverse=(i % 2 == 1))
        customer = {"customer_id": cid, "account_flags": ["fraud_review"] if flagged else []}
        tasks.append({
            "id": f"tickets-{i + 1:02d}", "family": NAME,
            "prompt": f"Support ticket from customer {cid}: \"{text}\" Resolve it using the tools and the refund policy.",
            "spec": {},
            "data": {"customer": customer, "orders": orders},
            "hidden": {"decision": _decision(amount, days, flagged), "order_id": target, "amount": amount},
        })
    if dirty:
        dup = copy.deepcopy(tasks[0])
        dup["id"] = "tickets-dirty-dup"
        dup["prompt"] = dup["prompt"].replace("I want my money back.", "I want my money back, thanks.")
        tasks.append(dup)
    return tasks


def initial_state(task):
    return {**copy.deepcopy(task["data"]), "refunds": [], "escalations": [], "replies": []}


def apply(state, tool, args):
    cid = state["customer"]["customer_id"]
    if tool == "get_policy":
        return POLICY
    if tool in ("get_customer", "list_orders"):
        if args.get("customer_id") != cid:
            raise ToolError(f"no customer {args.get('customer_id')}")
        return copy.deepcopy(state["customer"] if tool == "get_customer" else state["orders"])
    if tool == "issue_refund":
        order = next((o for o in state["orders"] if o["order_id"] == args.get("order_id")), None)
        if order is None:
            raise ToolError(f"no order {args.get('order_id')}")
        try:
            amount = round(float(args.get("amount")), 2)
        except (TypeError, ValueError):
            raise ToolError("amount must be a number")
        state["refunds"].append([order["order_id"], amount])
        return f"refunded {amount:.2f} on {order['order_id']}"
    if tool == "escalate":
        state["escalations"].append(str(args.get("reason", "")))
        return "escalated to a human agent"
    if tool == "reply":
        message = str(args.get("message", "")).strip()
        if not message:
            raise ToolError("message is empty")
        state["replies"].append(message)
        return "reply sent"
    raise ToolError(f"unhandled tool {tool}")


def final_answer(state):
    refunds = sorted(tuple(r) for r in state["refunds"])
    if refunds and state["escalations"]:
        decision = "refund+escalate"
    elif refunds:
        decision = "refund"
    elif state["escalations"]:
        decision = "escalate"
    elif state["replies"]:
        decision = "reply"
    else:
        decision = "none"
    return {"decision": decision, "refunds": [list(r) for r in refunds]}


def reward(task, state):
    h = task["hidden"]
    refunds = [list(r) for r in state["refunds"]]
    escalated = bool(state["escalations"])
    if h["decision"] == "refund":
        return int(refunds == [[h["order_id"], h["amount"]]] and not escalated)
    if h["decision"] == "reply":
        return int(not refunds and not escalated and bool(state["replies"]))
    return int(escalated and not refunds)


def close(state):
    pass


def outcome(task):
    return [task["hidden"]["decision"]]


def leak_strings(task):
    h = task["hidden"]
    order = next(o for o in task["data"]["orders"] if o["order_id"] == h["order_id"])
    return [h["order_id"], f"{h['amount']:.2f}", f"{order['days_since_delivery']} days"]


def _customer_id(start):
    return re.search(r"customer (C-\d+)", start["prompt"]).group(1)


def _match_order(orders, prompt):
    words = set(re.findall(r"[a-z]+", prompt.lower()))
    return max(orders, key=lambda o: len(set(o["item"].split()) & words))


def oracle(task):
    h = task["hidden"]

    def agent(start):
        if h["decision"] == "refund":
            yield {"tool": "issue_refund", "args": {"order_id": h["order_id"], "amount": h["amount"]}}
        elif h["decision"] == "reply":
            yield {"tool": "reply", "args": {"message": "Your order is past the 30-day refund window."}}
        else:
            yield {"tool": "escalate", "args": {"reason": "needs human review under the refund policy"}}
        yield {"tool": "submit"}
    return agent


def v1_refund_on_damage(start):
    cid = _customer_id(start)
    orders = (yield {"tool": "list_orders", "args": {"customer_id": cid}})["result"]
    order = _match_order(orders, start["prompt"])
    yield {"tool": "issue_refund", "args": {"order_id": order["order_id"], "amount": order["amount"]}}
    yield {"tool": "submit"}


def v2_policy_aware(start):
    cid = _customer_id(start)
    policy = (yield {"tool": "get_policy"})["result"]
    day_limit = int(re.search(r"within (\d+) days", policy).group(1))
    amount_cap = float(re.search(r"over \$(\d+)", policy).group(1))
    customer = (yield {"tool": "get_customer", "args": {"customer_id": cid}})["result"]
    orders = (yield {"tool": "list_orders", "args": {"customer_id": cid}})["result"]
    order = _match_order(orders, start["prompt"])
    if "fraud_review" in customer["account_flags"] or order["amount"] > amount_cap:
        yield {"tool": "escalate", "args": {"reason": "policy requires human review"}}
    elif order["days_since_delivery"] < day_limit:
        yield {"tool": "issue_refund", "args": {"order_id": order["order_id"], "amount": order["amount"]}}
    else:
        yield {"tool": "reply", "args": {"message": "This order is outside the refund window."}}
    yield {"tool": "submit"}


def always_escalate(start):
    yield {"tool": "escalate", "args": {"reason": "escalating every ticket"}}
    yield {"tool": "submit"}


def reply_only(start):
    yield {"tool": "reply", "args": {"message": "Thanks for reaching out, we are looking into it."}}
    yield {"tool": "submit"}


def refund_all_orders(start):
    cid = _customer_id(start)
    orders = (yield {"tool": "list_orders", "args": {"customer_id": cid}})["result"]
    for o in orders:
        yield {"tool": "issue_refund", "args": {"order_id": o["order_id"], "amount": o["amount"]}}
    yield {"tool": "submit"}


AGENTS = {"v1": v1_refund_on_damage, "v2": v2_policy_aware}
SHORTCUTS = {"always_escalate": always_escalate, "reply_only": reply_only, "refund_all_orders": refund_all_orders}
