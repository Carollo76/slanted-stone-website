# Reading the AI traffic data

The worker records a datapoint whenever a request comes from a known AI crawler,
or carries a referrer from an assistant. Reading it back needs a Cloudflare API
token. This is how to make one and use it safely.

## 1. Create the token

Cloudflare dashboard → **My Profile → API Tokens → Create Token → Create Custom
Token**.

| Field | Value |
|---|---|
| Name | `slantedstone-analytics-read` |
| Permissions | **Account** · **Account Analytics** · **Read** |
| Account Resources | Include · your account |
| TTL | optional — a year is reasonable |

One permission row, nothing else. This token can read analytics and do nothing
else: it cannot deploy, change DNS, or touch the Worker. If it ever leaks, the
blast radius is "someone saw the crawler counts."

**Copy it from the confirmation screen.** Cloudflare shows it once.

## 2. Put it in your shell without leaking it

In your terminal:

```
read -rs CLOUDFLARE_API_TOKEN && export CLOUDFLARE_API_TOKEN
```

Press Enter, paste the token at the blank prompt, press Enter again. `-s` means
it is not echoed to the screen, and because it is typed at a prompt rather than
written in the command, **it never enters your shell history**.

Then start Claude Code **from that same terminal**, so the variable is in its
environment.

Three things not to do:

- **Do not paste the token into a chat message.** This happened once with a
  Cloudflare token and it had to be revoked. Anything pasted into a
  conversation is stored.
- **Do not put it in a command**, e.g. `CLOUDFLARE_API_TOKEN=abc123 ...`. That
  is written to your history file and visible in `ps` to anything on the
  machine.
- **Do not commit it.** `.env` is not in this repo and should stay that way;
  the site takes roughly 200 distinct credential-probe requests a day.

## 3. Read it

```
scripts/ai_traffic.py          # last 7 days
scripts/ai_traffic.py 30       # last 30
```

Two tables: which AI operators are crawling and which are sending people, then
the most-fetched pages. **Crawls and referrals mean different things.** A crawl
is a bot fetching a page — it means the content is being collected. A referral
is a person who arrived from an assistant, which is the number that matters,
because it is the one that can turn into a booking.

## If it says authentication failed

The token is wrong or lacks the permission. Verify it by running the script —
that is the real test. Do not judge it by `/user/tokens/verify`: that endpoint
answers for a different kind of token and has already sent us down a blind
alley once, reporting `Invalid API Token` for a token that was fine.

## What this does not cover

GA4 (traffic, sources, the booking-domain hop) and Search Console (queries,
impressions, indexing) are separate systems with separate credentials. This
token reads only the Worker's own dataset.
