"""Build a short work plan against each outstanding due date."""

from itertools import combinations


def work_plan(bills, balance, matches, work):
    due_bills = sorted(
        (b for b in bills if b["state"] != "paid"), key=lambda b: b["due"]
    )
    candidates = {
        item["id"]: item
        for lane in matches
        for item in lane["jobs"]
        if item.get("reward")
        and item.get("payday")
        and item["kind"] != "external"
        and work.get(item["id"], {}).get("state") in (None, "revise")
    }
    required = sum(bill["cents"] for bill in due_bills) - balance
    if required <= 0 or not candidates:
        return None

    def shortfalls(bundle):
        available = balance
        gaps = []
        for bill in due_bills:
            available -= bill["cents"]
            arriving = sum(j["reward"] for j in bundle if j["payday"] <= bill["due"])
            gaps.append(max(0, -available - arriving))
        return tuple(gaps)

    def rank(bundle):
        return (
            shortfalls(bundle),
            sum(j["minutes"] for j in bundle),
            sum(j["reward"] for j in bundle),
            tuple(j["id"] for j in bundle),
        )

    # The executable buyer catalog contains at most three fixed-pay briefs.
    choices = (
        items
        for n in range(len(candidates) + 1)
        for items in combinations(candidates.values(), n)
    )
    best = min(choices, key=rank)
    if not best:
        return None
    return {
        "ids": [j["id"] for j in best],
        "reward": sum(j["reward"] for j in best),
        "minutes": sum(j["minutes"] for j in best),
        "remaining": shortfalls(best)[-1],
    }
