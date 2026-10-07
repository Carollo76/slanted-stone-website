#!/usr/bin/env python3
"""Add a first-party guest testimonial, with consent recorded.

Nothing reaches the site unless the guest actually sent the consent line. The
build re-checks this independently (.eleventy.js), so the two have to agree.

Usage:
  scripts/add_testimonial.py \
      --quote "We didn't want to leave. The sauna alone was worth the drive." \
      --first-name Dana --location "Hoboken, NJ" \
      --stay-month 2026-10 --party-type couple --consent-date 2026-11-02

Omit --consent-date when the guest did NOT send the consent line: the
testimonial is stored unpublished so the feedback is not lost.
"""
import argparse, json, re, sys, datetime, pathlib

DATA = pathlib.Path(__file__).resolve().parent.parent / "src/_data/testimonials.json"
WORDING = ("You may publish this on slantedstone.com with my first name "
           "and the month I stayed.")
PARTY_TYPES = ("family", "couple", "friends", "corporate", "solo")


def slugify(name, month):
    return re.sub(r"[^a-z0-9]+", "-", f"{name}-{month}".lower()).strip("-")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quote", required=True,
                   help="The guest's words, VERBATIM. Trim whole sentences if "
                        "needed; never reword.")
    p.add_argument("--first-name", required=True)
    p.add_argument("--location", default="", help='e.g. "Hoboken, NJ". Omit if '
                                                  "the guest did not volunteer it.")
    p.add_argument("--stay-month", required=True, help="YYYY-MM")
    p.add_argument("--party-type", required=True, choices=PARTY_TYPES)
    p.add_argument("--consent-date", default=None,
                   help="YYYY-MM-DD the guest sent the consent line. Omit if "
                        "they did not: the entry is saved unpublished.")
    a = p.parse_args()

    if not re.fullmatch(r"\d{4}-\d{2}", a.stay_month):
        sys.exit("--stay-month must be YYYY-MM")
    if a.consent_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.consent_date):
        sys.exit("--consent-date must be YYYY-MM-DD")

    quote = a.quote.strip()
    if len(quote) < 20:
        sys.exit("Refusing: that quote is too short to be a real guest sentence.")
    if quote.lower().startswith(("http", "www.")):
        sys.exit("Refusing: that looks like a link, not a guest's words.")

    doc = json.loads(DATA.read_text())
    items = [t for t in doc["items"] if t["id"] != "example-remove-me"]

    entry_id = slugify(a.first_name, a.stay_month)
    if any(t["id"] == entry_id for t in items):
        sys.exit(f"Refusing: '{entry_id}' already exists. Edit it by hand instead.")

    granted = a.consent_date is not None
    items.append({
        "id": entry_id,
        # approved tracks consent. There is deliberately no way to set it true
        # from the command line without a consent date.
        "approved": granted,
        "quote": quote,
        "guestFirstName": a.first_name,
        "guestLocation": a.location,
        "stayMonth": a.stay_month,
        "partyType": a.party_type,
        "source": "first-party",
        "permission": {
            "granted": granted,
            "grantedAt": a.consent_date,
            "scope": "website",
            "wording": WORDING,
        },
    })

    doc["items"] = items
    doc["updated"] = datetime.date.today().isoformat()
    DATA.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    if granted:
        print(f"Added '{entry_id}' and marked it for publication "
              f"(consent recorded {a.consent_date}).")
        print("Keep the guest's email — it is the evidence behind that flag.")
    else:
        print(f"Added '{entry_id}' UNPUBLISHED: no consent line was recorded.")
        print("Re-run with --consent-date if the guest later gives permission.")


if __name__ == "__main__":
    main()
