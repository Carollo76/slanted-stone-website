#!/usr/bin/env bash
# Pre-deployment verification for slantedstone.com.
#
#   ./scripts/preflight.sh http://127.0.0.1:8788        # local wrangler dev
#   ./scripts/preflight.sh https://<version>.workers.dev # preview version
#   ./scripts/preflight.sh https://slantedstone.com      # after promotion
#
# Exits non-zero if any check fails. Never run against production as a FIRST test.

set -uo pipefail
BASE="${1:?usage: preflight.sh <base-url>}"
PASS=0; FAIL=0

ok(){ printf "  \033[32mPASS\033[0m  %s\n" "$1"; PASS=$((PASS+1)); }
no(){ printf "  \033[31mFAIL\033[0m  %s\n" "$1"; FAIL=$((FAIL+1)); }

UA_BROWSER="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
code(){ curl -s -o /dev/null -w '%{http_code}' --max-time 20 -A "${2:-preflight}" "$1"; }
body(){ curl -s --max-time 20 -A "${2:-preflight}" "$1"; }

echo "── Assets serve ──────────────────────────────────"
for p in / /blog/ /privacy/ /robots.txt /sitemap.xml /llms.txt /feed.xml; do
  c=$(code "$BASE$p")
  [ "$c" = "200" ] && ok "$p → 200" || no "$p → $c (expected 200)"
done

# Every post listed in the sitemap must resolve.
SITEMAP_PATHS=$(body "$BASE/sitemap.xml" | grep -o '<loc>[^<]*</loc>' | sed 's/<\/*loc>//g' \
  | sed 's|https://slantedstone.com||')
while read -r p; do
  [ -z "$p" ] && continue
  c=$(code "$BASE$p")
  [ "$c" = "200" ] && ok "sitemap $p → 200" || no "sitemap $p → $c"
done <<< "$SITEMAP_PATHS"

echo
echo "── Images (must bypass worker, still serve) ──────"
c=$(code "$BASE/images/Hero%20front%20house.jpg")
[ "$c" = "200" ] && ok "hero image → 200" || no "hero image → $c"

echo
echo "── Booking CTAs resolve 200-direct ───────────────"
LINKS=$(body "$BASE/" | grep -oE 'https://[a-z0-9.-]*bookeddirectly\.[a-z]+[^"]*' | sed 's/&amp;/\&/g' | sort -u)
[ -z "$LINKS" ] && no "no booking links found on homepage"
while read -r u; do
  [ -z "$u" ] && continue
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "$u")
  lbl=$(echo "$u" | grep -o 'utm_content=[a-z_]*' || echo "no-utm")
  [ "$c" = "200" ] && ok "booking $lbl → 200 direct" || no "booking $lbl → $c (redirect or error)"
done <<< "$LINKS"

echo
echo "── Content correctness ───────────────────────────"
HOME=$(body "$BASE/" "GPTBot/1.0")
echo "$HOME" | grep -q "Slanted Stone Chalet" && ok "brand name in HTML" || no "brand name missing"
echo "$HOME" | grep -q 'id="rates"' && ok "rates block present" || no "rates block missing"
ROWS=$(echo "$HOME" | grep -oE '\$[0-9]+ – \$[0-9]+' | wc -l | tr -d ' ')
NIGHTS=$(echo "$HOME" | grep -oE '[0-9]+ nights' | wc -l | tr -d ' ')
if [ "$ROWS" -ge 3 ] && [ "$NIGHTS" -ge 3 ]; then
  ok "rates table renders $ROWS season rows with min-stay"
else
  no "rates table malformed ($ROWS price ranges, $NIGHTS min-stay cells)"
fi
echo "$HOME" | grep -q "aggregateRating" && no "aggregateRating present — must never be" || ok "no aggregateRating"
echo "$HOME" | grep -q "pocono-retreat%253A" && no "stale booking slug still present" || ok "no stale booking slug"
JSONLD=$(body "$BASE/" "$UA_BROWSER" | python3 -c '
import json,re,sys
h=sys.stdin.read()
blocks=re.findall(r"<script type=\"application/ld\+json\">(.*?)</script>",h,re.S)
if not blocks:
    print("NONE"); raise SystemExit
bad=[]
for b in blocks:
    try: json.loads(b)
    except Exception as e: bad.append(str(e)[:60])
print("OK %d" % len(blocks) if not bad else "BAD " + "; ".join(bad))
')
case "$JSONLD" in
  OK*) ok "${JSONLD#OK } JSON-LD block(s) parse" ;;
  NONE) no "no JSON-LD found (blocked or missing)" ;;
  *)   no "JSON-LD invalid: ${JSONLD#BAD }" ;;
esac

echo
echo "── Worker cannot break a response ────────────────"
for desc in "malformed-referer" "no-user-agent" "huge-user-agent" "ai-referral"; do
  case $desc in
    malformed-referer) c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -H "Referer: not-a-url:::" "$BASE/");;
    no-user-agent)     c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -H "User-Agent;" "$BASE/");;
    huge-user-agent)   c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -A "$(python3 -c 'print("x"*8000)')" "$BASE/");;
    ai-referral)       c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -H "Referer: https://chatgpt.com/c/x" "$BASE/");;
  esac
  [ "$c" = "200" ] && ok "$desc → 200" || no "$desc → $c"
done
c=$(code "$BASE/definitely-not-a-real-path-xyz")
[ "$c" = "404" ] && ok "missing path → 404 (worker does not mask)" || no "missing path → $c (expected 404)"

echo
echo "── AI crawler user-agents get full HTML ──────────"
for ua in "GPTBot/1.0" "ClaudeBot/1.0" "PerplexityBot/1.0" "Googlebot/2.1"; do
  n=$(body "$BASE/" "$ua" | wc -c | tr -d ' ')
  [ "$n" -gt 30000 ] && ok "$ua → ${n} bytes" || no "$ua → only ${n} bytes"
done

echo
echo "──────────────────────────────────────────────────"
echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
