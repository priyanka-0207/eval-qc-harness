from .scorers import REPORTED


def compare(before_cases, after_cases, metrics=REPORTED):
    before = {c["complaint_id"]: c for c in before_cases}
    out = {}
    for m in metrics:
        fixed, broken = [], []
        for c in after_cases:
            b = before.get(c["complaint_id"])
            if b is None:
                continue
            if not b[m] and c[m]:
                fixed.append(c["complaint_id"])
            elif b[m] and not c[m]:
                broken.append(c["complaint_id"])
        out[m] = {"fixed": len(fixed), "broken": len(broken),
                  "fixed_examples": fixed[:5], "broken_examples": broken[:5]}
    return out
