# Big Deals USA: handoff notes

Read this file before changing anything. It records how the app is set up, what lives outside this
repo, the rules that keep it working, and a log of past work. Add a log entry at the bottom whenever you change
something. `README.md` is older and partly out of date; where the two disagree, this file is right.

## What it is

Big Deals USA is a free phone web app (PWA) that lists big discounts from US stores. It refreshes
every 5 minutes. The deals come from the public deal list on blockbusterdeals.net (a WordPress and
WooCommerce site), and the app keeps that site's own buy links (they are its affiliate links).

- **Public URL:** https://bigdeals-usa.pages.dev/
- **Repo:** https://github.com/CharitIT/blockbuster-deals-app (public; the old name is kept because the URLs below depend on it)
- **GitHub Pages URL (still works, used as the origin):** https://charitit.github.io/blockbuster-deals-app/
- **Live deals Worker:** https://bbdeals.immadi-charit.workers.dev/ (`/check` runs the alert check by hand)

## How it fits together

```
blockbusterdeals.net (WordPress/WooCommerce public API)
   │                                   │
   │ every refresh (≤2 min cache)      │ GitHub's schedule (best effort, often hours late)
   ▼                                   ▼
Cloudflare Worker "bbdeals"        GitHub Actions "Update deals"
(worker/worker.js)                 (scripts/fetch_deals.py → commits deals.json, stores.json)
   │  + phone alerts via ntfy                  │
   │    every 5 min (cron)                     ▼
   │                                   GitHub Pages (hosts all app files)
   │                                           │
   │                                           ▼
   │                                   Cloudflare Pages "bigdeals-usa"
   │                                   (cloudflare-pages/_worker.js forwards every
   │                                    request to GitHub Pages; stores no files)
   ▼                                           ▼
            index.html in the phone: loads deals.json, then merges in the
            Worker's live deals (live ones first). Reloads every 5 min, when
            the app comes back to the screen, and on pull-to-refresh.
```

- **Updating the app:** push to `main`. GitHub Pages redeploys in about a minute and the
  `pages.dev` address shows the change right away. No Cloudflare step is needed.
- **The Worker does the live work.** GitHub's schedule can't be relied on: on 2026-11-20 and 21 it
  ran once in about 7 hours. `deals.json` from Actions is only a fallback and backfill.

## Files

| File | Purpose |
|---|---|
| `index.html` | The whole app: UI, filters, sort, search, refresh logic. `REFRESH_MS` (5 min) and `WORKER_URL` are near the top of the script. |
| `sw.js` | Service worker. Network-first for pages and `deals.json`, cache-first for icons. Ignores other origins (so the Worker is never cached). |
| `manifest.webmanifest` | App name, icons and colors for "Add to Home Screen". |
| `deals.json` / `stores.json` | Written by the bot. `stores.json` caches affiliate short link → real store name. |
| `manual.json` | Deals added by hand; merged into `deals.json`. |
| `scripts/fetch_deals.py` | Used by GitHub Actions. Standard library only. Also sends ntfy alerts if the `NTFY_TOPIC` secret is set (it is currently **not** set; the Worker sends alerts instead). |
| `.github/workflows/update-deals.yml` | Cron `*/5 * * * *` plus a manual "Run workflow" button. Commits only `deals.json` and `stores.json`. |
| `worker/worker.js` | Cloudflare Worker `bbdeals`. `GET /` returns live deals (CORS `*`, cached 120 s); the cron trigger sends ntfy alerts; `/check` does the same by hand. |
| Black Friday banner (in `index.html` + `worker/worker.js`) | Until 11:59 PM ET Dec 2, 2026 (`BF_END` in both files) the app shows a "Black Friday Deals" row above the search box, read live from the Google Sheet "ANLF BLACK FRIDAY YEAR DEALS 2026" through the Worker's `GET /blackfriday` (the sheet's CSV feed has no CORS header). Rows → deals: columns Item, Price, Coupon Code, Store, Notes ("Was $X (Y% off)"); rows with no price/store/link are section headings. The sheet has no product links, so cards open a store search (`SEARCH` map in the Worker). After Dec 2 the Worker returns nothing and the banner hides itself; the code can be removed any time after. |
| `cloudflare-pages/_worker.js` | Forwarder for the `bigdeals-usa` Pages project. `ORIGIN` points at the GitHub Pages URL. |
| `scripts/whatsapp_deals.py` + `scripts/com.blockbuster.deals.plist` | Manual fallback only, for when the site is down. Reads a WhatsApp Desktop database on a Mac. **Never run it together with the Actions schedule**, because both rewrite `deals.json`. |
| `patch_install.py`, `server.log` | Leftovers from earlier work; not used by the app. |

## Settings that live outside this repo

**Cloudflare** (dash.cloudflare.com, account subdomain `immadi-charit.workers.dev`):
- Worker `bbdeals`, with code pasted from `worker/worker.js` in the dashboard (**Edit code → paste → Deploy**). After changing `worker/worker.js`, redeploy it this same way. **Don't** run `wrangler deploy` for it without a config that recreates the bindings below, or they will be wiped.
  - KV binding: variable `SEEN` → namespace `bbdeals-seen` (IDs of deals already alerted)
  - Secret `NTFY_TOPIC`: the private ntfy topic. Its value is deliberately not written here because the repo is public. The owner has it in the ntfy phone app.
  - Optional text variable `MIN_DISCOUNT` (e.g. `20`)
  - Cron trigger `*/5 * * * *`
- Pages project `bigdeals-usa` (classic Pages, `pages.dev`), deployed from `cloudflare-pages/_worker.js`. See the rules below.

**GitHub** (repo Settings):
- Pages: deploy from branch `main`, root folder. **Must stay on, and the repo must stay public**, because the `pages.dev` site forwards to it.
- Actions secret `NTFY_TOPIC`: **deleted on purpose** so phones don't get the same alert twice. Leave it unset.

**The owner's Mac (gone once the local copy is deleted; nothing here is required):**
- Wrangler login (`npx wrangler login` again when needed).
- `~/Library/LaunchAgents/com.blockbuster.deals.plist`: installed but not loaded (the WhatsApp fallback).

## Rules that keep it working

1. **Run `git pull` before every push.** The bot commits to `main` up to every 5 minutes.
2. **Redeploying the Pages forwarder:** copy `cloudflare-pages/_worker.js` into an **empty** folder and run
   `npx wrangler pages deploy <that-folder> --project-name bigdeals-usa --branch main`.
   Never deploy from the repo root. Wrangler 4.16x once uploaded the whole repo, including ignored log files, as a public Worker.
   Do not create new Pages projects without `--force`. Without it, Wrangler now makes a `*.workers.dev` Worker
   instead of a `pages.dev` site.
3. **Renaming the repo, making it private or turning off GitHub Pages breaks `bigdeals-usa.pages.dev`.** If the
   repo is renamed, update `ORIGIN` in `cloudflare-pages/_worker.js` and redeploy it (rule 2).
4. **Copyright and trademark:** don't put "Blockbuster" in the app's name or UI. Don't copy the
   source's write-ups (`notes` is set to null on purpose) and don't store or commit product photos (the old
   `img/wa/` folder was deleted). Keep the source's buy links unchanged, the "View original post" link,
   and the "not affiliated" footer.
5. **Free-plan limits:** Cloudflare Workers allows 100k requests and 1k KV writes a day, and about
   10 ms of CPU time per request; current use is far below this. Don't move the app files to Cloudflare Pages builds,
   because the bot's commits would use up the 500 builds a month.
6. Keep `REFRESH_MS` at 5 minutes or more. 5 minutes is also GitHub's shortest possible cron.

## Run it locally

```bash
python3 -m http.server 8080   # then open http://localhost:8080
python3 scripts/fetch_deals.py   # rebuild deals.json from the site (the bot does this anyway)
```

## Open ideas (not done)

- Ask the blockbusterdeals.net owner for written permission to show their deal list.
- Optionally rename the GitHub repo to drop "blockbuster" (see rule 3 first).
- `README.md` is out of date in places (10-minute schedule, ntfy through GitHub). Bring it in line with this file.

## Activity log

Newest last. Dates are US Eastern.

- **2026-09-26:** App created. Deals from blockbusterdeals.net through GitHub Actions; auto refresh.
- **2026-09-27 to 09-29:** ntfy phone alerts from GitHub Actions; alerts for any deal from the last 12 h; prices.
- **2026-10-14:** Discount slider, category, store and price filters, sort, compact grid, pull to refresh,
  phone filter drawer, network-first service worker, real store names from affiliate links (`stores.json`).
- **2026-10-21:** blockbusterdeals.net went down.
- **2026-11-01:** Switched to the WhatsApp Desktop scanner (`scripts/whatsapp_deals.py`) on the Mac, with the Actions
  schedule turned off. App renamed "BlockbusterDealsIT". (No scheduled Actions runs from here until 11-20.)
- **2026-11-20:** Site back up. Actions schedule turned back on (10 min) and then set to 5 min.
- **2026-11-21:**
  - GitHub's schedule ran only once overnight (Black Friday load), so the Cloudflare Worker `bbdeals` was
    deployed and `WORKER_URL` was set in `index.html`. Live deals with prices now load on every refresh.
  - ntfy alerts moved to the Worker (KV `SEEN`, secret `NTFY_TOPIC` with a new random topic, 5-min cron).
    The GitHub `NTFY_TOPIC` secret was deleted.
  - Custom address: a first attempt made the Worker `usa-blockbuster-deals.immadi-charit.workers.dev`, which
    uploaded the whole repo folder, including the git-ignored `fetch_log.txt` (only public deal links). It was
    deleted after about 3 minutes. Then the Pages project `usa-blockbuster-deals` was created, later replaced.
  - Copyright and trademark cleanup: app renamed **Big Deals USA**; "not affiliated" footer with credit
    to the source; copied descriptions removed (`notes: null` in the bot, the Worker and the WhatsApp script);
    `img/wa/` photo copies deleted and no longer created; `scripts/__pycache__` removed from git.
  - New address **https://bigdeals-usa.pages.dev/** (Pages forwarder to GitHub Pages). The old
    `usa-blockbuster-deals` project was deleted.
  - This handoff file (`AGENTS.md`) was added.
  - **Black Friday Deals banner** added (until Dec 2): ~1,445 deals from the ANLF Black Friday Google Sheet,
    via the new Worker endpoint `/blackfriday`; swipe row of the top 20 by % off, "See all" switches the main list
    to the sheet's deals (filters/sort/search work). Also fixed `apple-mobile-web-app-title` (was "BB Deals")
    and made the page grid `minmax(0,1fr)` so wide rows can't widen the page.
