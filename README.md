# BlockbusterDeals Board (PWA)

A phone app for iPhone and Android that shows live offers from blockbusterdeals.net, the site behind the BlockbusterDeals 19 WhatsApp community.
It reloads every 5 minutes while it's open, and whenever you come back to it.

## Files

| File | What it does |
|---|---|
| `index.html` | The app: offer cards with photos, filters, search, copy-code buttons, live refresh |
| `deals.json` | The offers. Rewritten automatically by GitHub Actions |
| `manual.json` | Offers you add by hand (merged into `deals.json`) |
| `scripts/fetch_deals.py` | Pulls deals from blockbusterdeals.net |
| `.github/workflows/update-deals.yml` | Runs the script every 10 minutes |
| `manifest.webmanifest` | Name, icon and colors used when you install it on your phone |
| `sw.js` | Service worker: makes it installable and keeps the last offers available offline |
| `icons/` | App icons |

## Run it locally in Cursor

Open this folder in Cursor, then in its terminal:

```bash
python3 -m http.server 8080
```

Open http://localhost:8080. You need a server because opening `index.html` directly can't load `deals.json`.

## Put it online for free (GitHub Pages)

1. Create a new **public** repo on GitHub named `blockbuster-deals`. GitHub Pages is free for public repos.
2. In Cursor's terminal:
   ```bash
   git init
   git add .
   git commit -m "BlockbusterDeals Board PWA"
   git branch -M main
   git remote add origin https://github.com/<your-username>/blockbuster-deals.git
   git push -u origin main
   ```
3. On GitHub, go to the repo's **Settings → Pages → Build and deployment**. Choose **Deploy from a branch**, select `main` and `/ (root)`, then **Save**.
4. After about a minute the app is live at `https://<your-username>.github.io/blockbuster-deals/`.

## Install it on your phone

- **iPhone (Safari):** open the link, tap **Share**, then **Add to Home Screen**.
- **Android (Chrome):** open the link and tap **Install**, either in the app's banner or in Chrome's ⋮ menu.

It opens full-screen with its own icon, like a regular app.

## How offers get updated (fully automatic)

No WhatsApp and no Mac needed. The deals come from **blockbusterdeals.net**, the website behind the BlockbusterDeals WhatsApp community.

1. **GitHub Actions** runs `scripts/fetch_deals.py` every 10 minutes (`.github/workflows/update-deals.yml`). It reads the site's public product list (price, regular price, store link, photo, posted time), merges in `manual.json`, and commits `deals.json` only when something changed.
2. **GitHub Pages** redeploys within about a minute of that commit.
3. **The app** reloads `deals.json` every 5 minutes while open. It also reads the site's newest products directly, so a deal posted a minute ago shows up right away, marked "Just posted". Its price fills in after the next Actions run.

To run it right now: GitHub → **Actions** → **Update deals** → **Run workflow**.

WhatsApp-only offers that aren't on the website (for example HSN collections or sign-up offers) can be added by hand to `manual.json`.

## Note

A public repo means anyone with the link can see the offers. The offers come from the community's posts, so keep the link to yourself and your family.
