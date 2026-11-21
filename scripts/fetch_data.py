#!/usr/bin/env python3
"""Fetch the contribution calendar and featured-repo metadata.

Writes:
  data/contributions.json  -> [{"date": "YYYY-MM-DD", "count": int, "level": 0-4}, ...]
  data/repos.json          -> {"repo": {"description", "language", "stars", "forks", "url"}}

Usage:
  python scripts/fetch_data.py          # real data (GITHUB_TOKEN optional but recommended)
  python scripts/fetch_data.py --demo   # synthetic data for local previews
"""
import datetime as dt
import html
import json
import os
import random
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
USER = CFG["username"]
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)


def http(url, data=None, headers=None):
    h = {"User-Agent": f"{USER}-profile-readme"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


# ---------------------------------------------------------------- contributions
def contributions_graphql():
    q = """query($login:String!){user(login:$login){contributionsCollection{
      contributionCalendar{weeks{contributionDays{date contributionCount contributionLevel}}}}}}"""
    body = json.dumps({"query": q, "variables": {"login": USER}}).encode()
    res = json.loads(http("https://api.github.com/graphql", body,
                          {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"}))
    weeks = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    lv = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
    return [{"date": d["date"], "count": d["contributionCount"], "level": lv.get(d["contributionLevel"], 0)}
            for w in weeks for d in w["contributionDays"]]


def contributions_scrape():
    page = http(f"https://github.com/users/{USER}/contributions")
    cells = {}
    for m in re.finditer(r"<td[^>]*?data-date=\"([\d-]+)\"[^>]*?>", page):
        tag = m.group(0)
        cid = re.search(r'id="([^"]+)"', tag)
        lvl = re.search(r'data-level="(\d)"', tag)
        cells[cid.group(1) if cid else m.group(1)] = {
            "date": m.group(1), "count": 0, "level": int(lvl.group(1)) if lvl else 0}
    for m in re.finditer(r'<tool-tip[^>]*for="([^"]+)"[^>]*>(.*?)</tool-tip>', page, re.S):
        txt = html.unescape(m.group(2))
        n = re.match(r"\s*([\d,]+) contribution", txt)
        if m.group(1) in cells and n:
            cells[m.group(1)]["count"] = int(n.group(1).replace(",", ""))
    days = sorted(cells.values(), key=lambda d: d["date"])
    if not days:
        raise RuntimeError("no contribution cells found (GitHub markup changed?)")
    return days


def contributions_demo():
    random.seed(7)
    today = dt.date.today()
    start = today - dt.timedelta(days=364 + (today.weekday() + 1) % 7)
    days, d = [], start
    while d <= today:
        season = 0.55 + 0.45 * abs(((d - start).days / 365 * 2.2) % 2 - 1)
        busy = random.random() < (0.35 if d.weekday() >= 5 else 0.7) * season
        c = int(random.expovariate(1 / 5)) + 1 if busy else 0
        days.append({"date": d.isoformat(), "count": c,
                     "level": 0 if c == 0 else min(4, 1 + c // 4)})
        d += dt.timedelta(days=1)
    return days


# ---------------------------------------------------------------- repos
def repos_live():
    out = {}
    hdr = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        hdr["Authorization"] = f"Bearer {TOKEN}"
    for r in CFG["repos"]:
        try:
            j = json.loads(http(f"https://api.github.com/repos/{USER}/{r['name']}", headers=hdr))
            out[r["name"]] = {"description": j.get("description") or "", "language": j.get("language") or "",
                              "stars": j.get("stargazers_count", 0), "forks": j.get("forks_count", 0),
                              "url": j.get("html_url")}
        except Exception as e:  # keep going, renderer falls back to config.json
            print(f"  ! repo {r['name']}: {e}", file=sys.stderr)
    return out


def main():
    demo = "--demo" in sys.argv
    if demo:
        days = contributions_demo()
        repos = {}
    else:
        # Scrape first: it mirrors the public profile (incl. private contributions if you enabled
        # "Private contributions" in profile settings). GraphQL is the fallback.
        try:
            days = contributions_scrape()
            print("contributions: scraped")
        except Exception as e:
            if not TOKEN:
                raise
            print(f"  ! scrape failed ({e}), using GraphQL", file=sys.stderr)
            days = contributions_graphql()
            print("contributions: GraphQL")
        repos = repos_live()
    (DATA / "contributions.json").write_text(json.dumps(days, indent=0))
    (DATA / "repos.json").write_text(json.dumps(repos, indent=2))
    print(f"{len(days)} days, {sum(d['count'] for d in days)} contributions, {len(repos)} repos")


if __name__ == "__main__":
    main()
