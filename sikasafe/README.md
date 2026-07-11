# SikaSafe — guard your MoMo from scams

**A free, offline web app that helps ordinary Ghanaians spot mobile-money (MoMo)
scams before they lose money.** *Sika / shika* means money in Akan and Gã.

Paste a suspicious text, or pick what's happening to you, and SikaSafe explains —
in plain language — whether it looks like a scam, *why*, and exactly what to do.
It also teaches the common tricks and tells you who to call if you've been hit.

**No install needed. No account. No ads. Nothing you type ever leaves your phone.**

## Why this

Mobile money is how millions of Ghanaians hold and move money — and fraud is
surging. Cyber-fraud losses jumped from GH₵2.4M (Q1 2024) to **GH₵14.9M in the
first half of 2025**, reported fraud cases rose **48%** to 24,778, and
mobile-money/fintech providers accounted for **97%** of them. SIM-swap and
social-engineering scams lead the way, and the root cause regulators keep
naming is **low awareness**, not broken technology. That's a gap an app can
close — by putting scam-spotting and the right emergency steps in everyone's
pocket, offline, in the languages people actually speak.

Sources: [The Fourth Estate](https://thefourthestategh.com/2025/10/mobile-money-robberies-inside-ghanas-rising-cybercrime-wave/),
[TechLabari](https://techlabari.com/mobile-money-fraud-surges-in-ghana-as-digital-payments-outpace-security/),
[Cyber Security Authority](https://www.csa.gov.gh/mobile_money_fraud.php).

## What it does

- **Check** — paste an SMS/WhatsApp message and get a clear verdict
  (Danger / Be careful / No obvious signs) with the exact red flags it found and
  what each one means. Or tap a situation ("someone says they sent me money by
  mistake", "a caller wants my PIN"…) for instant, specific guidance. Analysis
  runs **entirely on the phone** — the text is never uploaded.
- **The 7 golden rules** — the short list that stops most scams, shareable to
  WhatsApp in one tap so you can protect family too.
- **Learn** — the scams doing the rounds in Ghana (fake "wrong transfer", fake
  agent/customer-care, promo/prize, dial-a-code, SIM-swap, pay-a-fee-first),
  each with how it works, its warning signs, and how to beat it.
- **Reports** — flag a scam number and look numbers up. Offline, reports stay on
  your phone; connect a **community server** (below) and lookups/reports use a
  shared, crowd-sourced blocklist — a number is shown as *flagged* only once
  several different people report it.
- **Help** — "Scammed? Do this now" step-by-step, plus one-tap official
  contacts to freeze your wallet and report.

## Verified reporting contacts

- **Cyber Security Authority (CSA):** call/SMS **292**, WhatsApp **0501603111**,
  `report@csa.gov.gh` — [csa.gov.gh/report](https://www.csa.gov.gh/report)
- **Bank of Ghana – Consumer Protection:** `consumerprotection@bog.gov.gh`,
  0302 686 401
- **Networks:** MTN **100** · Telecel **0501 000 000** · AirtelTigo **0599 000 000**

## Languages

English and **Ghanaian Pidgin** are complete. **Gã** is included as an early
**community draft** and is clearly marked as such in the app — it should be
reviewed by a native Gã speaker before people rely on it. Adding or correcting a
language is just editing the `en` / `pcm` / `gaa` fields in
[`js/data.js`](js/data.js); anything left untranslated falls back to English.
**Contributions from Gã, Twi, Ewe, Dagbani and Hausa speakers are very welcome.**

## Run it

It's a static site — no build step.

```bash
cd sikasafe
python3 -m http.server 8000   # then open http://localhost:8000
```

Deploy free on GitHub Pages or Netlify (a `netlify.toml` is included). It's a
PWA: on a phone, "Add to Home Screen" installs it, and it then works offline.

## Community mode (optional)

The app is fully useful offline. To make scam-number reports **shared across the
whole community**, run the small backend in [`server/`](server/) (dependency-free
Python + SQLite) and connect the app to it — either set `DEFAULT_API` in
[`js/api.js`](js/api.js) for everyone, or let each user paste the server URL under
**Reports → Community server**. See [`server/README.md`](server/README.md) for the
API and free deploy options (Render / Railway / Fly). The backend only ever
flags a number once several *distinct* people report it, so one bad report can't
brand a number.

```bash
python3 server/server.py          # runs the community API
python3 server/test_server.py     # 12 backend tests
```

## How it's built

100% client-side: vanilla HTML/CSS/JS, no framework, no backend, no tracking.
The scam analyzer is a transparent set of weighted red-flag rules in
[`js/detector.js`](js/detector.js) — every verdict lists the signals it matched,
so it teaches while it checks. Content lives in [`js/data.js`](js/data.js).

## Limitations (read these)

- SikaSafe gives **guidance, not guarantees**. It can't see your MoMo account,
  and "no obvious signs" or "not reported" never means "safe."
- The analyzer catches known scam **patterns**; new wording can slip past it.
  Always fall back to the golden rules — above all, never share your PIN/OTP.
- Without a community server, number reports are **local to your phone**. With
  one, they're shared — but the server is a solid foundation, not a hardened
  production service (see [`server/README.md`](server/README.md) for the honest
  limits: moderation/appeals and anti-poisoning hardening are future work).
- It is an **independent public-safety tool**, not affiliated with any network,
  bank, or agency. Verify contacts against your provider's official materials.

## License

[MIT](LICENSE.txt). Built to be forked, translated, and improved by the
community. Fraud figures and reporting contacts sourced from the CSA, Bank of
Ghana, and Ghanaian reporting linked above.
