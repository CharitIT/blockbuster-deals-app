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
from urllib.parse import urlparse, unquote

SITE = "https://blockbusterdeals.net"
COUNT = 60
ROOT = Path(__file__).resolve().parent.parent
OUT, MANUAL = ROOT / "deals.json", ROOT / "manual.json"
LOG_FILE = ROOT / "fetch_log.txt"
UA = {"User-Agent": "Mozilla/5.0 (BlockbusterDeals Board; +https://charitit.github.io/blockbuster-deals-app/)",
      "Accept": "application/json"}


def log(msg):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}\n"
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def money(minor, unit):
    if minor in (None, ""):
        return None
    v = int(minor) / (10 ** unit)
    return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"


# Store web domains (exact domain or a subdomain of it).
MERCHANTS = (("amazon.com", "Amazon"), ("amzn.to", "Amazon"), ("amzn.com", "Amazon"), ("a.co", "Amazon"), ("link.amazon", "Amazon"),
             ("walmart.com", "Walmart"), ("target.com", "Target"), ("hsn.com", "HSN"), ("qvc.com", "QVC"),
             ("macys.com", "Macy's"), ("kohls.com", "Kohl's"), ("bestbuy.com", "Best Buy"), ("nordstromrack.com", "Nordstrom"),
             ("nordstrom.com", "Nordstrom"), ("jcpenney.com", "JCPenney"), ("homedepot.com", "Home Depot"), ("lowes.com", "Lowe's"),
             ("costco.com", "Costco"), ("samsclub.com", "Sam's Club"), ("ulta.com", "Ulta"), ("sephora.com", "Sephora"),
             ("oldnavy.com", "Old Navy"), ("oldnavy.gap.com", "Old Navy"), ("gap.com", "Gap"), ("nike.com", "Nike"),
             ("adidas.com", "Adidas"), ("wayfair.com", "Wayfair"), ("ebay.com", "eBay"), ("ebay.us", "eBay"),
             ("curology.com", "Curology"), ("dickssportinggoods.com", "Dick's"), ("bjs.com", "BJ's"),
             ("bedbathandbeyond.com", "Bed Bath & Beyond"), ("overstock.com", "Overstock"), ("zappos.com", "Zappos"),
             ("chewy.com", "Chewy"), ("dell.com", "Dell"), ("lenovo.com", "Lenovo"), ("samsung.com", "Samsung"),
             ("michaelkors.com", "Michael Kors"), ("calvinklein.us", "Calvin Klein"), ("belk.com", "Belk"),
             ("dillards.com", "Dillard's"), ("saksoff5th.com", "Saks Off 5th"), ("tjmaxx.tjx.com", "TJ Maxx"),
             ("marshalls.com", "Marshalls"), ("rossstores.com", "Ross"), ("victoriassecret.com", "Victoria's Secret"),
             ("ulta.com", "Ulta"), ("ae.com", "American Eagle"), ("abercrombie.com", "Abercrombie"), ("hollisterco.com", "Hollister"),
             ("jcrew.com", "J.Crew"), ("loft.com", "LOFT"), ("lululemon.com", "Lululemon"), ("underarmour.com", "Under Armour"),
             ("ikea.com", "IKEA"), ("crocs.com", "Crocs"), ("skechers.com", "Skechers"), ("coach.com", "Coach"),
             ("coachoutlet.com", "Coach"), ("katespade.com", "Kate Spade"), ("katespadeoutlet.com", "Kate Spade"),
             ("vera bradley.com".replace(" ", ""), "Vera Bradley"), ("newegg.com", "Newegg"), ("gamestop.com", "GameStop"),
             ("staples.com", "Staples"), ("officedepot.com", "Office Depot"), ("petsmart.com", "PetSmart"), ("cvs.com", "CVS"),
             ("walgreens.com", "Walgreens"), ("temu.com", "Temu"), ("shein.com", "SHEIN"), ("aliexpress.us", "AliExpress"))
# apple.com is only a store when the link actually lands there (never from an App Store badge on a redirect page).
KNOWN = {name for _, name in MERCHANTS}
SHORTENERS = ("mavely", "sylikes", "magik.ly", "bit.ly", "tinyurl", "linksynergy", "sjv.io", "go.skimresources",
              "howl.me", "shopmy", "rstyle", "click.linksynergy", "theblogcm")


def merchant_for(host):
    host = (host or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    for dom, name in MERCHANTS:
        if host == dom or host.endswith("." + dom):
            return name
    return None


STORES = ROOT / "stores.json"   # cache: link -> merchant (or "" when unknown)


def load_store_cache():
    try:
        return json.loads(STORES.read_text())
    except Exception:
        return {}


UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
NEXT_HOP = re.compile(r"""(?:http-equiv=["']?refresh["']?[^>]*url=|location(?:\.href)?\s*=\s*|location\.replace\(\s*|window\.open\(\s*)["']?(https?://[^"'\s<>)]+)""", re.I)
ANY_URL = re.compile(r"https?://(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})", re.I)

# Store-brand names -> store (used when a link can't be followed).
HOUSE_BRANDS = (
    ("Walmart", ("athletic works", "ozark trail", "mainstays", "no boundaries", "wonder nation", "garanimals", "time and tru",
                 "better homes & gardens", "better homes and gardens", "george ", "terra & sky", "great value", "equate",
                 "parent's choice", "hyper tough", "onn.", "onn ", "pen + gear", "allswell", "gap home", "sofia jeans",
                 "scoop ", "free assembly", "avia ", "my texas house")),
    ("Target", ("cat & jack", "goodfellow", "threshold", "room essentials", "a new day", "wild fable", "universal thread",
                "all in motion", "hearth & hand", "pillowfort", "up&up", "brightroom", "opalhouse", "art class")),
    ("HSN", ("curtis stone", "joy mangano", "colleen lopez", "hsn ")),
    ("QVC", ("denim & co", "isaac mizrahi live", "cook's essentials")),
    ("Kohl's", ("sonoma goods for life", "so juniors", "tek gear", "food network ", "lc lauren conrad", "simply vera")),
    ("Macy's", ("charter club", "style & co", "inc international", "alfani", "club room", "hotel collection")),
    ("Amazon", ("amazon essentials", "amazon basics", "amazonbasics")),
)


def merchant_from_title(title):
    t = " " + (title or "").lower() + " "
    for store, brands in HOUSE_BRANDS:
        if any(b in t for b in brands):
            return store
    return None


def _open(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA_MOBILE, "Accept": "text/html,*/*"})
    return urllib.request.urlopen(req, timeout=10)


def resolve_merchant(url, cache, budget):
    """Follow an affiliate short link (and up to 3 JS/meta-refresh hops) to learn the real store. Cached per link."""
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
    found, nxt = "", url
    seen = {url}
    try:
        for _ in range(4):
            with _open(nxt) as r:
                land = urlparse(r.geturl()).netloc.lower()
                found = merchant_for(land) or ("Apple" if land in ("apple.com", "www.apple.com") else "")
                if found:
                    break
                body = html.unescape(unquote(r.read(300000).decode("utf-8", "ignore")))
            hop = NEXT_HOP.search(body)
            if hop:
                hop_url = hop.group(1)
                if hop_url in seen:
                    break
                nxt = hop_url
                seen.add(nxt)
                found = merchant_for(urlparse(nxt).netloc) or ""
                for m in ([] if found else ANY_URL.finditer(nxt[8:])):  # store URL embedded in the hop's query string
                    found = merchant_for(m.group(1)) or ""
                    if found:
                        break
                if found:
                    break
                continue
            for m in ANY_URL.finditer(body):  # last resort: any store URL mentioned in the page
                found = merchant_for(m.group(1)) or ""
                if found:
                    break
            break
    except Exception as e:
        log(f"resolve failed: {url} - {e}")
        return None  # don't cache failures; try again next run
    cache[url] = found
    return found or None


def store_for(url, cats, cache=None, budget=None, title=""):
    m = resolve_merchant(url, cache if cache is not None else {}, budget or [0]) or merchant_from_title(title)
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
            "store": store_for(buy, cats, cache, budget, html.unescape(p.get("name") or "")),
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
    
    # Merge manual offers before calculating which links to keep in cache
    if MANUAL.exists():
        offers += json.loads(MANUAL.read_text()).get("offers", [])
    
    keep = {o["link"] for o in offers if o.get("link")}
    STORES.write_text(json.dumps({k: v for k, v in cache.items() if k in keep}, indent=1, sort_keys=True) + "\n")
    
    offers.sort(key=lambda o: o.get("postedAt") or "", reverse=True)
    return offers


def main():
    log("Starting scan...")
    offers = build()
    if not offers:
        log("No offers returned; leaving deals.json unchanged.")
        sys.exit("No offers returned; leaving deals.json unchanged.")
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    if old.get("offers") == offers:
        log("No changes detected since last scan.")
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_ids = {o["id"] for o in old.get("offers", [])}
    added = [o for o in offers if o["id"] not in old_ids]
    log(f"Found {len(added)} new offer(s).")
    log("Updating deals.json...")
    log_entries = ([{"at": now, "text": f"{len(added)} new offer(s): " + ", ".join(o['title'][:40] for o in added[:3])}] if added else []) + old.get("log", [])
    OUT.write_text(json.dumps({
        "channel": "BlockbusterDeals 19",
        "source": SITE,
        "lastScan": now,
        "nextScan": None,
        "offers": offers,
        "log": log_entries[:20],
    }, indent=2, ensure_ascii=False) + "\n")
    log(f"Wrote {len(offers)} offers ({len(added)} new).")
    notify(added, now)
    log("Scan complete.")


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
        log(f"Notified {len(fresh)} deal(s).")
    except Exception as e:  # never fail the update because of a notification
        log(f"Notification failed: {e}")


if __name__ == "__main__":
    main()
