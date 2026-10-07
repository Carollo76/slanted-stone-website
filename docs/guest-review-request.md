# Post-stay review request

Collects the only review text this property can legally publish: first-party,
given directly by the guest, with explicit permission to publish it.

**Why this exists.** Airbnb's terms restrict copying their review content, and
Google prohibits aggregating ratings from other sites, so nothing from the
Airbnb listing or the Elfsight widget can be pasted into the site. Google also
treats reviews a business collects about itself as self-serving, which is why
there is no `aggregateRating` or `review` markup anywhere on the site and no
rating field in `testimonials.json`. What we publish is plain on-page
testimonial text that assistants and humans can read.

**No incentive, ever.** The 15% direct-booking discount is never mentioned in
the same message as the review ask, and a review is never a condition of any
discount. Incentivised reviews breach platform policy and taint the rest.

---

## The automation

Set up once in Uplisting → automated guest messaging.

- **Trigger:** 1 day after checkout
- **Channel:** email (not SMS — we need room for the consent sentence)
- **Applies to:** direct bookings. OTA guests already review on the OTA; asking
  them to send review text to us instead can read as review diversion.

Swap `GUEST_FIRST_NAME` for Uplisting's merge tag before saving.

### Subject

```
Did the sauna get used, GUEST_FIRST_NAME?
```

### Body

```
Hi GUEST_FIRST_NAME,

Thanks for staying at Slanted Stone. I hope the Poconos treated you well and
that you got at least one quiet evening in the hot tub.

If you have a minute, I'd love to hear how it went — just hit reply. Two or
three sentences is plenty. What you'd tell a friend who asked whether the
place was worth it is exactly the right thing.

If you're happy for me to use your words on the website, add this line to your
reply and I'll take it as a yes:

  "You may publish this on slantedstone.com with my first name and the month
  I stayed."

No pressure at all — I'd genuinely like the feedback either way, and I won't
publish anything without that line.

Thanks again,
Christian
Slanted Stone Chalet
```

### Why it is worded that way

- **Reply-to-email, not a form.** Fewest steps, and the reply is a durable
  written record of consent sitting in the inbox.
- **The consent sentence is quoted verbatim** and matches `permission.wording`
  in `testimonials.json`, so the record and the published page agree.
- **First name and month only** — the guest is told exactly what will appear.
  No surname, no full location unless they volunteer it.
- **"either way"** keeps the feedback honest. A message that only wants praise
  gets praise.

---

## Turning a reply into a published testimonial

1. Confirm the reply contains the consent line. **No line, no publish** — file
   the feedback and move on.
2. Run `scripts/add_testimonial.py` (see `--help`). It refuses to record
   consent that was not given, quotes the guest verbatim, and stamps the date.
3. Commit. The build itself re-checks: `.eleventy.js` fails the build if any
   testimonial is `approved: true` without `permission.granted: true`, so a
   mistake here stops the deploy rather than going live.
4. Keep the guest's email. It is the evidence behind the consent flag.

## Editing rules

Publish the guest's words verbatim. Trimming for length is fine; tightening
their grammar is not, and adding adjectives they did not write is fabrication.
If a quote needs a cut, cut whole sentences from the ends, never reword the
middle. If a guest later asks to be removed, set `approved: false` and deploy.
