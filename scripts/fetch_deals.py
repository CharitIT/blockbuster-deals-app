"""Build deals.json from blockbusterdeals.net (the site behind the BlockbusterDeals WhatsApp community).

Runs in GitHub Actions. Standard library only.
- Prices, store links and images come from the public WooCommerce Store API.
- Posted times come from the WordPress REST API.
- Offers in manual.json (WhatsApp-only deals that aren't on the site) are merged in.
deals.json is only rewritten when the offer list actually changes, so GitHub Pages
doesn't redeploy for nothing.
"""
import html, json, re, sys, urllib.request
from datetime import datetime, timezone
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


def store_for(url, cats):
    host = urlparse(url or "").netloc.lower()
    if "amzn" in host or "amazon" in host:
        return "Amazon"
    for key, name in (("walmart", "Walmart"), ("target", "Target"), ("hsn", "HSN"), ("qvc", "QVC"), ("macys", "Macy's")):
        if key in host:
            return name
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
            "store": store_for(buy, cats),
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


if __name__ == "__main__":
    main()
