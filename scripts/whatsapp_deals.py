"""Build deals.json from the Blockbuster Deals WhatsApp community, using WhatsApp Desktop's local database.

Runs on a Mac signed in to WhatsApp Desktop (launchd, every 10 minutes; see scripts/com.blockbuster.deals.plist).
Standard library + macOS `sips` only.
- Reads only the announcement group named CHAT, read-only. Nothing is sent to WhatsApp.
- Each post is an image with a caption like "$6🔥 At Walmart / Reg$11 / <title> / <link> / #ad".
- Images are shrunk into img/wa/ so GitHub Pages can serve them.
- New offers are merged into deals.json (newest COUNT kept), then committed and pushed.
"""
import json, os, re, sqlite3, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_deals import (KNOWN, MANUAL, OUT, ROOT, STORES, load_store_cache, log, merchant_for,
                         merchant_from_title, notify, resolve_merchant)

CHAT = os.environ.get("WA_CHAT", "Blockbuster Deals 32")
COUNT = 60
WA = Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared"
DB = WA / "ChatStorage.sqlite"
IMG = ROOT / "img" / "wa"
APPLE_EPOCH = 978307200  # Core Data dates count seconds from 2001-01-01

PRICE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d\d)?)")
REG = re.compile(r"\breg(?:ular)?\.?\s*:?\s*\$\s?(\d[\d,]*(?:\.\d\d)?)", re.I)
AT_STORE = re.compile(r"\bat\s+([A-Z][\w'&.]*(?:\s[A-Z][\w'&.]*)?)")
URL = re.compile(r"https?://\S+")
CODE = re.compile(r"\b(?i:code|coupon)[ \t]*:?[ \t]*([A-Z0-9]{4,})\b")
# Hashtags, hype headers and Woot's checkout boilerplate; never the product title.
NOISE = re.compile(r"^(#ad|limited time deal|lightning deal|deal selling fast|selling fast|hot deal|price drop|back in stock)\W*$"
                   r"|woot is an amazon company|^at checkout login", re.I)


def posts():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        # Session type 1 is the group itself; the community parent (type 4) has the same name.
        row = con.execute("SELECT Z_PK FROM ZWACHATSESSION WHERE ZPARTNERNAME LIKE ? AND ZSESSIONTYPE = 1 "
                          "ORDER BY ZLASTMESSAGEDATE DESC LIMIT 1", (f"%{CHAT}%",)).fetchone()
        if not row:
            return []
        return con.execute(
            "SELECT m.ZSTANZAID, m.ZMESSAGEDATE, COALESCE(i.ZTITLE, m.ZTEXT, ''), i.ZMEDIALOCALPATH "
            "FROM ZWAMESSAGE m LEFT JOIN ZWAMEDIAITEM i ON i.Z_PK = m.ZMEDIAITEM "
            "WHERE m.ZCHATSESSION = ? ORDER BY m.ZMESSAGEDATE DESC LIMIT ?", (row[0], COUNT)).fetchall()
    finally:
        con.close()


def money(s):
    v = float(s.replace(",", ""))
    return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"


def image(stanza, local):
    """Copy the post's photo into img/wa/ at 480px, once. Returns the site-relative path."""
    if not local:
        return None
    src, dst = WA / "Message" / local, IMG / f"{stanza}.jpg"
    if not dst.exists():
        if not src.exists():
            return None  # not downloaded yet; picked up on a later run
        IMG.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["sips", "-Z", "480", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                            str(src), "--out", str(dst)], capture_output=True)
        if r.returncode:
            return None
    return f"img/wa/{dst.name}"


def parse(stanza, date, caption, local, cache, budget):
    lines = [l.strip() for l in caption.splitlines() if l.strip()]
    link = next((m.group(0) for l in lines for m in [URL.search(l)] if m), None)
    if not link:
        return None  # chatter, not a deal
    price = was = store = None
    rest = []
    for l in lines:
        if URL.search(l) or NOISE.match(l):
            continue
        reg = REG.search(l)
        if reg:
            was = was or money(reg.group(1))
            continue
        p = PRICE.search(l)
        if p and not price and ("🔥" in l or len(l) < 40):
            price = ("As low as " if "low as" in l.lower() else "") + money(p.group(1))
            at = AT_STORE.search(l)
            store = merchant_for_name(at.group(1)) if at else None
            continue
        if re.search(r"[A-Za-z]{3}", l):
            rest.append(l)
    if not rest:
        return None
    title = max(rest, key=len)  # product names are the long line; "Clip coupon" / "Free shipping" are notes
    rest.remove(title)
    if "woot" in caption.lower():
        store, rest = "Woot", rest + ["Sign in with your Amazon account at checkout for free shipping."]
    store = store or resolve_merchant(link, cache, budget) or merchant_from_title(title)
    disc = None
    pv, wv = (float(PRICE.search(x).group(1).replace(",", "")) if x else None for x in (price, was))
    if pv and wv and wv > pv:
        disc = f"{round(100 * (1 - pv / wv))}% off"
    code = CODE.search(caption)
    o = {
        "id": f"wa-{stanza}",
        "store": store or "Deal",
        "title": title,
        "price": price,
        "was": was if disc else None,
        "discount": disc,
        "code": code.group(1) if code else None,
        "notes": " ".join(rest)[:160] or None,
        "link": link,
        "page": None,
        "image": image(stanza, local),
        "category": None,
        "postedAt": datetime.fromtimestamp(date + APPLE_EPOCH, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expiresAt": None,
        "status": "active",
        "source": "whatsapp",
    }
    if o["store"] in KNOWN:
        o["merchant"] = o["store"]
    return o


def merchant_for_name(name):
    """'Walmart' / 'Target' / 'Best Buy' from an "At <Store>" line."""
    n = name.lower().strip(" .")
    return next((k for k in KNOWN if k.lower() == n), None) or merchant_for(n.replace(" ", "") + ".com")


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def main():
    log("Starting WhatsApp scan...")
    try:
        rows = posts()
    except sqlite3.Error as e:
        sys.exit(f"Can't read WhatsApp database ({e}). Is WhatsApp Desktop installed and does python3 have Full Disk Access?")
    pull = git("pull", "--rebase", "--autostash", "-q")
    if pull.returncode:
        log(f"git pull failed: {pull.stderr.strip()}")
    cache = load_store_cache()
    budget = [40]
    fresh = [o for o in (parse(*r, cache, budget) for r in rows) if o]
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    manual = json.loads(MANUAL.read_text()).get("offers", []) if MANUAL.exists() else []
    manual_ids = {o["id"] for o in manual}
    # Keep earlier offers (WhatsApp Desktop only holds recent posts); a post's newest parse wins.
    # Website offers (blockbusterdeals.net, down since 2026-10-21) are dropped: their prices are stale.
    merged = {o["id"]: o for o in old.get("offers", []) if o["id"] not in manual_ids and o.get("source") != "site"}
    merged.update({o["id"]: o for o in fresh})
    offers = sorted(merged.values(), key=lambda o: o.get("postedAt") or "", reverse=True)[:COUNT] + manual
    offers.sort(key=lambda o: o.get("postedAt") or "", reverse=True)

    keep = {o["link"] for o in offers if o.get("link")}
    STORES.write_text(json.dumps({k: v for k, v in cache.items() if k in keep}, indent=1, sort_keys=True) + "\n")
    used = {Path(o["image"]).name for o in offers if (o.get("image") or "").startswith("img/wa/")}
    for f in IMG.glob("*.jpg") if IMG.exists() else []:
        if f.name not in used:
            f.unlink()

    if old.get("offers") == offers:
        log("No changes detected since last scan.")
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_ids = {o["id"] for o in old.get("offers", [])}
    added = [o for o in offers if o["id"] not in old_ids]
    log_entries = ([{"at": now, "text": f"{len(added)} new offer(s): " + ", ".join(o['title'][:40] for o in added[:3])}] if added else []) + old.get("log", [])
    OUT.write_text(json.dumps({
        "channel": CHAT,
        "source": "whatsapp",
        "lastScan": now,
        "nextScan": None,
        "offers": offers,
        "log": log_entries[:20],
    }, indent=2, ensure_ascii=False) + "\n")
    log(f"Wrote {len(offers)} offers ({len(added)} new).")
    notify(added, now)

    if os.environ.get("WA_NO_PUSH"):
        return
    paths = ("deals.json", "stores.json", "img/wa")
    git("add", "-A", *paths)
    if git("diff", "--cached", "--quiet", "--", *paths).returncode == 0:
        return
    # Commit only these paths, never anything else that happens to be staged.
    git("commit", "-q", "-m", f"Update deals {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC (WhatsApp)", "--", *paths)
    push = git("push", "-q")
    log("Pushed." if push.returncode == 0 else f"git push failed: {push.stderr.strip()}")


if __name__ == "__main__":
    main()
