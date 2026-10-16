#!/usr/bin/env python3
"""Read the AI-crawler and assistant-referral data the worker records.

The worker (worker/index.js) writes a datapoint whenever a request arrives from
a known AI crawler user-agent, or carries a referrer from an assistant. This
reads it back.

Needs a Cloudflare API token with Account Analytics -> Read, in the environment
as CLOUDFLARE_API_TOKEN. See docs/analytics-access.md. The token is read from
the environment only, never from an argument: an argument would land in your
shell history and in the process list where other users can see it.

Usage:  scripts/ai_traffic.py [days]      (default 7)
"""
import json, os, sys, urllib.request, urllib.error

ACCOUNT_ID = "501bf7ea89ce447e4bedf9796715e6e2"
DATASET = "slantedstone_ai_traffic"
URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/analytics_engine/sql"


def query(sql, token):
    req = urllib.request.Request(
        URL, data=sql.encode(), headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            doc = json.loads(body)
            msgs = "; ".join(
                f"{x.get('code')}: {x.get('message')}" for x in doc.get("errors", [])
            )
        except Exception:
            msgs = body[:300]
        sys.exit(
            f"\nCloudflare rejected the query (HTTP {e.code}).\n  {msgs}\n\n"
            "If this says the token is invalid or lacks permission, the token "
            "needs Account -> Account Analytics -> Read on this account.\n"
        )
    try:
        return json.loads(body).get("data", [])
    except json.JSONDecodeError:
        sys.exit(f"Unexpected response:\n{body[:300]}")


def main():
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        sys.exit(
            "CLOUDFLARE_API_TOKEN is not set. In your terminal:\n"
            "  read -rs CLOUDFLARE_API_TOKEN && export CLOUDFLARE_API_TOKEN\n"
            "then paste the token at the blank prompt and press Enter. Start "
            "Claude Code from that same terminal.\n"
        )
    days = sys.argv[1] if len(sys.argv) > 1 else "7"
    if not days.isdigit():
        sys.exit("days must be a whole number")

    # _sample_interval is the sampling weight Analytics Engine applies.
    # Summing double1 on its own undercounts whenever sampling kicks in.
    rows = query(
        f"SELECT blob1 AS kind, blob2 AS operator, "
        f"SUM(_sample_interval * double1) AS hits "
        f"FROM {DATASET} WHERE timestamp > NOW() - INTERVAL '{days}' DAY "
        f"GROUP BY kind, operator ORDER BY hits DESC FORMAT JSON",
        token,
    )

    print(f"=== AI crawlers and assistant referrals, last {days} days ===")
    if not rows:
        print("  no rows — nothing recorded in this window")
        return
    for title, kind in (
        ("CRAWLS  (bots fetching pages)", "crawl"),
        ("REFERRALS  (people arriving from an assistant)", "referral"),
    ):
        group = sorted(
            (r for r in rows if r["kind"] == kind),
            key=lambda r: -float(r["hits"]),
        )
        print(f"\n  {title}")
        if not group:
            print("    none")
            continue
        for r in group:
            print(f"    {r['operator']:<24}{float(r['hits']):>10,.0f}")
        print(f"    {'TOTAL':<24}{sum(float(r['hits']) for r in group):>10,.0f}")

    paths = query(
        f"SELECT blob3 AS path, SUM(_sample_interval * double1) AS hits "
        f"FROM {DATASET} WHERE timestamp > NOW() - INTERVAL '{days}' DAY "
        f"GROUP BY path ORDER BY hits DESC LIMIT 15 FORMAT JSON",
        token,
    )
    if paths:
        print("\n=== most-fetched pages ===")
        for r in paths:
            print(f"  {r['path'][:56]:<58}{float(r['hits']):>9,.0f}")


if __name__ == "__main__":
    main()
