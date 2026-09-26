# BlockbusterDeals Board (PWA)

A phone app for iPhone and Android that shows offers from the BlockbusterDeals 19 WhatsApp community.
It reloads `deals.json` every hour while it's open, and again whenever you come back to it after an hour.

## Files

| File | What it does |
|---|---|
| `index.html` | The app: offer cards, filters, search, copy-code buttons, hourly refresh |
| `deals.json` | The offers. Claude rewrites this file after each WhatsApp scan |
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

## How offers get updated

1. Claude scans the WhatsApp community (Announcements only) on your Mac.
2. Claude updates `deals.json` in this folder, then commits and pushes it.
3. GitHub Pages redeploys in about a minute.
4. The app picks up the new offers at its next hourly refresh, or right away when you tap **Refresh**.

To update it by hand, edit `deals.json` and push. Each offer looks like this:

```json
{ "id": "unique-id", "store": "HSN", "title": "Item name", "price": "$67", "was": "$99",
  "discount": "32% off", "code": "WELCOME2026", "notes": "…", "link": "https://…",
  "postedAt": "2026-09-26T17:43:00Z", "expiresAt": null, "status": "active" }
```

Set `"status": "expired"` or a past `expiresAt` to move an offer to the Expired tab.

## Note

A public repo means anyone with the link can see the offers. The offers come from the community's posts, so keep the link to yourself and your family.
