#!/usr/bin/env python3
"""
Refresh src/_data/rates.json from PriceLabs.

Publishes seasonal *ranges* only — never date-level availability. See the audit
report for the reasoning: a static build cannot honestly represent availability
that changes minute to minute, and the feed's availability semantics are
ambiguous (demand_desc "Unavailable" appears both with and without a
booking_status, so it cannot be mapped to "booked" with confidence).

Env:
  PRICELABS_API_KEY  required
  PRICELABS_API_URL  optional override; confirm the path against the Swagger docs
                     linked from PriceLabs → Account Settings → API Details.
"""

import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

LISTING_ID = "200887"
PMS_NAME = "uplisting"
DEFAULT_URL = "https://api.pricelabs.co/v1/listing_prices"
OUT = "src/_data/rates.json"
HORIZON_DAYS = 365

# (label, months blurb, start month, end month) — end is inclusive, wraps at year end.
SEASONS = [
    ("Winter", "January – February", 1, 2),
    ("Spring", "March – May", 3, 5),
    ("Summer", "June – August", 6, 8),
    ("Fall & foliage", "September – October", 9, 10),
    ("Late fall", "November – mid December", 11, 11),
]


def fetch(api_key, url):
    today = date.today()
    payload = {
        "listings": [
            {
                "id": LISTING_ID,
                "pms": PMS_NAME,
                "dateFrom": (today + timedelta(days=1)).isoformat(),
                "dateTo": (today + timedelta(days=HORIZON_DAYS)).isoformat(),
            }
        ]
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "X-API-Key": api_key,
            "Content-Type": "application/json",
            # api.pricelabs.co sits behind Cloudflare, which 403s urllib's default
            # "Python-urllib/x.y" User-Agent. curl works, urllib does not.
            "User-Agent": "slantedstone-rates/1.0 (+https://slantedstone.com)",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def extract_days(raw):
    """Tolerate both the bare-list and {'data': [...]} envelope shapes."""
    body = raw.get("data", raw) if isinstance(raw, dict) else raw
    if isinstance(body, list) and body and isinstance(body[0], dict) and "data" in body[0]:
        return body[0]["data"]
    if isinstance(body, list):
        return body
    raise ValueError(f"unrecognised response shape: {type(body)}")


def summarise(days):
    by_month = {}
    for d in days:
        try:
            month = int(d["date"][5:7])
            price = float(d["price"])
            min_stay = int(d.get("min_stay") or 2)
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        by_month.setdefault(month, []).append((price, min_stay))

    seasons = []
    for label, months, start, end in SEASONS:
        vals = [v for m in range(start, end + 1) for v in by_month.get(m, [])]
        if not vals:
            continue
        prices = [p for p, _ in vals]
        stays = [s for _, s in vals]
        seasons.append(
            {
                "key": label.lower().split()[0].strip("&"),
                "label": label,
                "months": months,
                "from": int(min(prices)),
                "to": int(max(prices)),
                "typical": int(statistics.median(prices)),
                "minStay": int(statistics.mode(stays)),
            }
        )

    all_prices = [p for vals in by_month.values() for p, _ in vals]
    if not all_prices:
        raise ValueError("no usable prices in response")

    return {
        "updated": date.today().isoformat(),
        "currency": "USD",
        "source": f"PriceLabs listing {LISTING_ID} ({PMS_NAME})",
        "coverage": "rolling-365",
        "coverageNote": f"Rolling {HORIZON_DAYS}-day pull, refreshed nightly.",
        "disclaimer": "Nightly rates before fees and taxes. Final total is shown at checkout.",
        "checkinTime": "16:00",
        "checkoutTime": "10:00",
        "lowestNightly": int(min(all_prices)),
        "highestNightly": int(max(all_prices)),
        "seasons": seasons,
    }


def main():
    api_key = os.environ.get("PRICELABS_API_KEY")
    if not api_key:
        sys.exit("PRICELABS_API_KEY is not set")

    url = os.environ.get("PRICELABS_API_URL") or DEFAULT_URL
    try:
        raw = fetch(api_key, url)
    except urllib.error.HTTPError as e:
        hint = {
            403: "Check PRICELABS_API_KEY is the full key (40 chars) and that the "
                 "Customer API is enabled on the account.",
            404: "Wrong endpoint path — override with the PRICELABS_API_URL variable.",
            401: "PRICELABS_API_KEY is not valid.",
        }.get(e.code, "Check the endpoint path and key.")
        sys.exit(f"PriceLabs returned HTTP {e.code} for {url}. {hint}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach PriceLabs: {e.reason}")

    try:
        doc = summarise(extract_days(raw))
    except ValueError as e:
        sys.exit(f"Could not parse PriceLabs response: {e}")

    # Refuse to publish an implausible band rather than overwrite good data.
    if doc["lowestNightly"] < 50 or doc["highestNightly"] > 5000:
        sys.exit(
            f"Refusing to write implausible range "
            f"${doc['lowestNightly']}-${doc['highestNightly']}"
        )

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print(f"Wrote {OUT}: ${doc['lowestNightly']}-${doc['highestNightly']}, "
          f"{len(doc['seasons'])} seasons")


if __name__ == "__main__":
    main()
