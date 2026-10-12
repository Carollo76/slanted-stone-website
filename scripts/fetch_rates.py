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

# Seasons are bucketed by (month, day), not by month alone.
#
# They used to be month ranges ending at ("Late fall", ..., 11, 11) — so month 12
# belonged to no season and December never appeared in the published table at
# all, while the "Late fall" label claimed to cover "mid December". The gap sat
# over the most valuable inventory of the year: the nights of 18 Dec – 2 Jan ask
# far more than any other season and carry a 3-night minimum over Christmas and
# New Year. A guest reading the old table saw "typical $310, 2 nights".
#
# Order here is the order rendered.
SEASONS = [
    ("winter", "Winter", "January – February", (1, 3), (2, 29)),
    ("spring", "Spring", "March – May", (3, 1), (5, 31)),
    ("summer", "Summer", "June – August", (6, 1), (8, 31)),
    ("fall", "Fall & foliage", "September – October", (9, 1), (10, 31)),
    ("late", "Late fall", "November – mid December", (11, 1), (12, 17)),
    ("holidays", "Christmas & New Year", "18 December – 2 January", (12, 18), (1, 2)),
]


def season_key(month, day):
    """Which season a date falls in. Ranges may wrap the year end."""
    for key, _label, _blurb, (sm, sd), (em, ed) in SEASONS:
        start, end, here = (sm, sd), (em, ed), (month, day)
        if start <= end:
            if start <= here <= end:
                return key
        elif here >= start or here <= end:   # wraps December into January
            return key
    return None


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
    buckets = {}
    for d in days:
        try:
            month = int(d["date"][5:7])
            day = int(d["date"][8:10])
            price = float(d["price"])
            min_stay = int(d.get("min_stay") or 2)
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        key = season_key(month, day)
        if key is None:
            continue
        buckets.setdefault(key, []).append((price, min_stay))

    seasons = []
    for key, label, months, _start, _end in SEASONS:
        vals = buckets.get(key)
        if not vals:
            continue
        prices = [p for p, _ in vals]
        stays = [s for _, s in vals]
        seasons.append(
            {
                "key": key,
                "label": label,
                "months": months,
                "from": int(min(prices)),
                "to": int(max(prices)),
                "typical": int(statistics.median(prices)),
                # max, not mode. A season can mix 2- and 3-night minimums, and
                # the two failure directions are not symmetric: telling someone
                # 2 nights when the night they want needs 3 sends them to a
                # checkout that refuses them, which is the exact mismatch this
                # block exists to prevent. Quoting the stricter number is a
                # smaller error than quoting one that does not hold.
                "minStay": int(max(stays)),
            }
        )

    all_prices = [p for vals in buckets.values() for p, _ in vals]
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
