"""Each scout reads a brief feed, then asks a local model to explain its matches."""

import json, os, urllib.request
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent / "data/opportunities.json").read_text())
AGENTS = ("Speech", "Evaluation", "Licensing")


def scout(agent, profile):
    candidates = [
        x
        for x in CATALOG
        if x["agent"] == agent
        and x["minutes"] <= profile["minutes"]
        and x["lang"] in ("any", profile["language"])
        and (x["kind"] != "photo" or profile["photos"])
    ]
    rows = [
        dict(
            x,
            reason=f"Fits your {profile['minutes']}-minute window.",
            source="Get By test buyer",
        )
        for x in candidates
    ]
    for row in rows:
        payday = row.get("payday")
        due = profile.get("due")
        if payday:
            relation = (
                " · after next bill"
                if due and payday > due
                else " · by next bill"
                if due
                else ""
            )
            row["timing"] = payday + relation + " (test buyer estimate)"
        else:
            row["timing"] = "When a license sells · may carry to another cycle"
    if not rows:
        return {"agent": agent, "engine": "Eligibility check", "jobs": []}
    base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    prompt = (
        "For this work matching app explain each eligible job's fit in one specific short English sentence. "
        "Use language and time constraints. Never invent money, verification, affiliation or availability. "
        'Return JSON {"matches":[{"id":"...","reason":"..."}]}. '
        + json.dumps(
            {
                "profile": profile,
                "jobs": [
                    {
                        k: x[k]
                        for k in ("id", "title", "brief", "lang", "minutes", "payday")
                    }
                    for x in candidates
                ],
            }
        )
    )
    try:
        data = json.dumps(
            {
                "model": model,
                "stream": False,
                "format": "json",
                "prompt": prompt,
                "options": {"temperature": 0, "num_predict": 230, "num_ctx": 4096},
            }
        ).encode()
        req = urllib.request.Request(
            base + "/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=150) as res:
            content = json.load(res)["response"]
        matches = json.loads(content)["matches"]
        reasons = {
            v["id"]: v["reason"].strip()[:250]
            for v in matches
            if isinstance(v, dict) and isinstance(v.get("reason"), str)
        }
        if any(not reasons.get(x["id"]) for x in rows):
            raise ValueError
        for x in rows:
            x["reason"] = reasons[x["id"]]
        return {"agent": agent, "engine": model, "jobs": rows}
    except (OSError, ValueError, TypeError, KeyError):
        return {
            "agent": agent,
            "engine": "Eligibility rules · model unavailable",
            "jobs": rows,
        }
