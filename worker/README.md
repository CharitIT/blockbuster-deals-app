# BlockbusterDeals Worker (Cloudflare, free)

Gives the app live prices (price, original price, % off, you save) for every deal, and sends
ntfy phone alerts every 5 minutes. Replaces the slow GitHub schedule for alerts.

## Set up (about 10 minutes, all in the browser)

1. Sign up free at https://dash.cloudflare.com/sign-up
2. **Workers & Pages → Create → Create Worker**. Name it `bbdeals` → **Deploy**.
3. **Edit code** → delete the sample → paste all of `worker.js` → **Deploy**.
   Open the worker URL (`https://bbdeals.<you>.workers.dev/`): you should see JSON with deals and prices.
4. **Storage & Databases → KV → Create** a namespace called `bbdeals-seen`.
5. Back in the worker: **Settings → Bindings → Add → KV namespace**. Variable name `SEEN`, namespace `bbdeals-seen`.
6. **Settings → Variables and Secrets → Add**:
   - `NTFY_TOPIC` (type **Secret**) = your ntfy topic
   - `MIN_DISCOUNT` (type Text) = `20` (optional)
7. **Settings → Triggers → Add Cron Trigger** → `*/5 * * * *`.
8. Test: open `https://bbdeals.<you>.workers.dev/check`. First time it says
   `first run: remembered 40 deals, no alerts`; after that `alerted N`.
9. Put the worker URL in `index.html` → `const WORKER_URL = "https://bbdeals.<you>.workers.dev/";` and push.
10. Remove the `NTFY_TOPIC` secret from GitHub (Settings → Secrets) so you don't get double alerts.
