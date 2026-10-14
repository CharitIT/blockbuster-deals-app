"""Build deals.json from blockbusterdeals.net (the site behind the BlockbusterDeals WhatsApp community).

Runs in GitHub Actions. Standard library only.
- Prices, store links and images come from the public WooCommerce Store API.
- Posted times come from the WordPress REST API.
- Offers in manual.json (WhatsApp-only deals that aren't on the site) are merged in.
deals.json is only rewritten when the offer list actually changes, so GitHub Pages
doesn't redeploy for nothing.
"""
import html, json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

SITE = "https://blockbusterdeals.net"
COUNT = 60
ROOT = Path(__file__).resolve().parent.parent
OUT, MANUAL = ROOT / "deals.json", ROOT / "manual.json"
UA = {"User-Agent": "Mozilla/5.0 (BlockbusterDeals Board; +https://charitit.github.io/blockbuster-deals-app/)",
      "Accept": "application/json"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def money(minor, unit):
    if minor in (None, ""):
        return None
    v = int(minor) / (10 ** unit)
    return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"


MERCHANTS = (("amzn", "Amazon"), ("amazon", "Amazon"), ("walmart", "Walmart"), ("target.com", "Target"),
             ("hsn.com", "HSN"), ("qvc", "QVC"), ("macys", "Macy's"), ("kohls", "Kohl's"), ("bestbuy", "Best Buy"),
             ("nordstromrack", "Nordstrom"), ("nordstrom", "Nordstrom"), ("jcpenney", "JCPenney"), ("homedepot", "Home Depot"),
             ("lowes", "Lowe's"), ("costco", "Costco"), ("samsclub", "Sam's Club"), ("ulta", "Ulta"), ("sephora", "Sephora"),
             ("oldnavy", "Old Navy"), ("gap.com", "Gap"), ("nike", "Nike"), ("adidas", "Adidas"), ("wayfair", "Wayfair"),
             ("ebay", "eBay"), ("curology", "Curology"))
KNOWN = {name for _, name in MERCHANTS}
SHORTENERS = ("mavely", "sylikes", "magik.ly", "bit.ly", "tinyurl", "linksynergy", "sjv.io", "go.skimresources",
              "howl.me", "shopmy", "rstyle", "click.linksynergy", "theblogcm")


def merchant_for(host):
    host = (host or "").lower()
    for key, name in MERCHANTS:
        if key in host:
            return name
    return None


STORES = ROOT / "stores.json"   # cache: link -> merchant (or "" when unknown)


def load_store_cache():
    try:
        return json.loads(STORES.read_text())
    except Exception:
        return {}


def resolve_merchant(url, cache, budget):
    """Follow an affiliate short link once to learn the real store. Cached per link."""
    if not url:
        return None
    direct = merchant_for(urlparse(url).netloc)
    if direct:
        return direct
    if url in cache:
        return cache[url] or None
    if budget[0] <= 0 or not any(k in url for k in SHORTENERS):
        return None
    budget[0] -= 1
    found = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            found = merchant_for(urlparse(r.geturl()).netloc) or ""
            if not found:  # some shorteners use a JS/meta redirect: look for a store URL in the page
                body = r.read(200000).decode("utf-8", "ignore")
                for m in re.finditer(r"https?://(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})", body):
                    found = merchant_for(m.group(1)) or ""
                    if found:
                        break
    except Exception as e:
        print("resolve failed:", url, e)
        return None  # don't cache failures; try again next run
    cache[url] = found
    return found or None


def store_for(url, cats, cache=None, budget=None):
    m = resolve_merchant(url, cache if cache is not None else {}, budget or [0])
    if m:
        return m
    return cats[0] if cats else "Deal"


DISCLAIMER = re.compile(r"(this post contains affiliate links|as an amazon associate|prices and availability are accurate)", re.I)


def text(s, limit=160):
    # First paragraph only, and skip the site's boilerplate affiliate disclaimer.
    paras = [p for p in re.split(r"</p>|<br\s*/?>|\n", s or "") if p.strip()]
    paras = [p for p in paras if not DISCLAIMER.search(p)]
    s = html.unescape(re.sub(r"<[^>]+>", " ", paras[0] if paras else ""))
    s = re.sub(r"\s+", " ", s).strip()
    return (s[: limit - 1] + "…") if len(s) > limit else s


def build():
    products = get(f"{SITE}/wp-json/wc/store/v1/products?per_page={COUNT}&orderby=date&order=desc")
    dates = {p["id"]: p["date_gmt"] for p in get(f"{SITE}/wp-json/wp/v2/product?per_page={COUNT}&_fields=id,date_gmt")}
    offers = []
    cache = load_store_cache()
    budget = [40]   # max new links to resolve per run
    for p in products:
        pr = p.get("prices") or {}
        unit = int(pr.get("currency_minor_unit") or 2)
        price, reg = pr.get("price"), pr.get("regular_price")
        disc = None
        if price and reg and int(reg) > int(price) > 0:
            disc = f"{round(100 * (1 - int(price) / int(reg)))}% off"
        cats = [html.unescape(c["name"]) for c in p.get("categories") or []]
        buy = (p.get("add_to_cart") or {}).get("url") or p.get("permalink")
        posted = dates.get(p["id"])
        offers.append({
            "id": f"bbd-{p['id']}",
            "store": store_for(buy, cats, cache, budget),
            "title": html.unescape(p.get("name") or "").strip(),
            "price": money(price, unit),
            "was": money(reg, unit) if disc else None,
            "discount": disc,
            "code": None,
            "notes": text(p.get("short_description") or p.get("description")),
            "link": buy,
            "page": p.get("permalink"),
            "image": ((p.get("images") or [{}])[0]).get("thumbnail") or ((p.get("images") or [{}])[0]).get("src"),
            "category": cats[0] if cats else None,
            "postedAt": (posted + "Z") if posted else None,
            "expiresAt": None,
            "status": "active" if p.get("is_in_stock", True) else "expired",
            "source": "site",
        })
    for o in offers:
        if o["store"] in KNOWN:
            o["merchant"] = o["store"]
    keep = {o["link"] for o in offers}
    STORES.write_text(json.dumps({k: v for k, v in cache.items() if k in keep}, indent=1, sort_keys=True) + "\n")
    if MANUAL.exists():
        offers += json.loads(MANUAL.read_text()).get("offers", [])
    offers.sort(key=lambda o: o.get("postedAt") or "", reverse=True)
    return offers


def main():
    offers = build()
    if not offers:
        sys.exit("No offers returned; leaving deals.json unchanged.")
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    if old.get("offers") == offers:
        print("No change.")
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_ids = {o["id"] for o in old.get("offers", [])}
    added = [o for o in offers if o["id"] not in old_ids]
    log = ([{"at": now, "text": f"{len(added)} new offer(s): " + ", ".join(o['title'][:40] for o in added[:3])}] if added else []) + old.get("log", [])
    OUT.write_text(json.dumps({
        "channel": "BlockbusterDeals 19",
        "source": SITE,
        "lastScan": now,
        "nextScan": None,
        "offers": offers,
        "log": log[:20],
    }, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(offers)} offers ({len(added)} new).")
    notify(added, now)


# ---------- Phone notifications via ntfy (https://ntfy.sh) ----------
# Set the repo secret NTFY_TOPIC to your private topic name to turn this on.
# Optional repo variable NTFY_MIN_DISCOUNT (e.g. 40) only alerts for deals at least that % off.
def pct(o):
    m = re.match(r"(\d+)% off", o.get("discount") or "")
    return int(m.group(1)) if m else 0


def ntfy(topic, payload):
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(dict(payload, topic=topic)).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=15).read()


def notify(added, now):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic or not added:
        return
    min_off = int(os.environ.get("NTFY_MIN_DISCOUNT") or 0)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Only deals posted in the last 12 hours (GitHub can delay runs by hours), so the first run or a long pause does not send a flood.
    fresh = [o for o in added if (o.get("postedAt") or "") >= cutoff and pct(o) >= min_off]
    app = "https://charitit.github.io/blockbuster-deals-app/"
    try:
        if len(fresh) > 4:
            ntfy(topic, {"title": f"{len(fresh)} new deals", "tags": ["shopping_cart"], "click": app,
                         "message": "\n".join(f"{o.get('price') or ''} · {o['title'][:60]}" for o in fresh[:8])})
        else:
            for o in fresh:
                head = " · ".join(x for x in (o.get("price"), o.get("discount")) if x)
                msg = {"title": (head + " — " if head else "") + o["title"][:80],
                       "message": " · ".join(x for x in (o.get("store"), ("was " + o["was"]) if o.get("was") else None) if x) or "New deal",
                       "tags": ["shopping_cart"], "click": o.get("link") or app,
                       "actions": [{"action": "view", "label": "Open app", "url": app}]}
                if o.get("image"):
                    msg["attach"] = o["image"]
                ntfy(topic, msg)
        print(f"Notified {len(fresh)} deal(s).")
    except Exception as e:  # never fail the update because of a notification
        print("Notification failed:", e)


if __name__ == "__main__":
    main()
