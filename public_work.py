"""Discover public briefs without sending a user's profile or documents outside the app."""

import json
import re
import urllib.parse
import urllib.request

SEARCH = "https://api.github.com/search/issues"
QUERIES = {
    "documentation": "is:issue is:open no:assignee label:bounty documentation",
    "design": "is:issue is:open no:assignee label:bounty design",
}


def public_work(payload):
    category = payload.get("category", "documentation")
    if category not in QUERIES:
        raise ValueError("Select a supported public work category.")
    query = urllib.parse.urlencode(
        {"q": QUERIES[category], "sort": "updated", "order": "desc", "per_page": 8}
    )
    request = urllib.request.Request(
        SEARCH + "?" + query,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Get-By-Opportunity-Scout",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            items = json.load(response)["items"]
    except (OSError, ValueError, KeyError) as exc:
        raise ValueError("Public search is unavailable. Try again later.") from exc
    jobs = []
    for issue in items:
        url = issue.get("html_url", "")
        match = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)/issues/\d+", url)
        if match and issue.get("state") == "open" and not issue.get("pull_request"):
            jobs.append(
                {"title": issue["title"][:160], "url": url, "source": match.group(1)}
            )
    return {"jobs": jobs}
