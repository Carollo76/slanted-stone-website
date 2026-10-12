#!/usr/bin/env python3
"""One-time Pinterest OAuth bootstrap.

Why this exists: PINTEREST_ACCESS_TOKEN was set on 2026-04-08 as a static
value. Pinterest v5 access tokens live 30 days, so it died around 8 May 2026
and every share since has failed on "Authentication failed." Pasting a fresh
access token just restarts that 30-day clock. This stores a REFRESH token
instead, and the workflow mints a short-lived access token on each run.

Secrets are read with getpass and handed straight to `gh secret set`. Nothing
sensitive is printed, echoed, or written to disk.

Run:  scripts/pinterest_auth.py
"""
import base64, getpass, json, secrets, subprocess, sys, urllib.parse, urllib.request

TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
AUTH_URL = "https://www.pinterest.com/oauth/"
# pins:write to create the pin, boards:read so a wrong board id fails loudly.
SCOPES = "boards:read,pins:read,pins:write"


def post_token(app_id, app_secret, params):
    basic = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(params).encode(),
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"\nPinterest rejected the exchange ({e.code}):\n{body}\n")


def gh_secret(name, value):
    subprocess.run(["gh", "secret", "set", name], input=value.encode(),
                   check=True)
    print(f"  stored {name}")


def main():
    print(__doc__)
    print("From https://developers.pinterest.com/apps/ — your app's credentials.")
    app_id = input("App ID: ").strip()
    app_secret = getpass.getpass("App secret (hidden): ").strip()
    redirect = input("A redirect URI listed on the app "
                     "[https://slantedstone.com/]: ").strip() or "https://slantedstone.com/"
    if not app_id or not app_secret:
        sys.exit("App ID and secret are both required.")

    state = secrets.token_urlsafe(16)
    q = urllib.parse.urlencode({
        "client_id": app_id, "redirect_uri": redirect,
        "response_type": "code", "scope": SCOPES, "state": state,
    })
    print("\n1. Open this URL and approve the app:\n")
    print(f"   {AUTH_URL}?{q}\n")
    print("2. You land on a page that may well 404 — that is fine. Copy the\n"
          "   WHOLE address bar: the ?code=... is what matters.\n")
    landed = input("Paste the full redirect URL: ").strip()

    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(landed).query)
    code = (parsed.get("code") or [None])[0]
    if not code:
        sys.exit("No ?code= found in that URL.")
    if (parsed.get("state") or [None])[0] != state:
        sys.exit("state mismatch — do not continue; start over.")

    tok = post_token(app_id, app_secret, {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect,
        # Apps created before 25 Sep 2025 need this for a continuously
        # refreshable token; on newer apps it is the default and is ignored.
        "continuous_refresh": "true",
    })

    refresh = tok.get("refresh_token")
    if not refresh:
        sys.exit(f"No refresh_token returned. Response keys: {list(tok)}")

    print("\nExchange succeeded.")
    print(f"  access token expires in : {tok.get('expires_in')}s")
    rexp = tok.get("refresh_token_expires_in")
    print(f"  refresh token expires in: {rexp}s"
          f"{f' (~{int(rexp)//86400} days)' if rexp else ' (not stated)'}")

    print("\nStoring secrets...")
    gh_secret("PINTEREST_APP_ID", app_id)
    gh_secret("PINTEREST_APP_SECRET", app_secret)
    gh_secret("PINTEREST_REFRESH_TOKEN", refresh)

    print("\nDone. PINTEREST_ACCESS_TOKEN is now unused — delete it with:")
    print("  gh secret delete PINTEREST_ACCESS_TOKEN")


if __name__ == "__main__":
    main()
