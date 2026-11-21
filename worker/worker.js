// Big Deals USA Worker (Cloudflare Workers, free plan)
//
// 1. GET https://<your-worker>.workers.dev/  -> newest deals from blockbusterdeals.net
//    WITH price, original price and % off, readable by the phone app (CORS enabled).
// 2. Cron trigger (every 5 min) -> sends an ntfy phone alert for each new deal.
// 3. GET /blackfriday -> the Black Friday Google Sheet as deals (until Dec 2), for the app's banner.
//
// Settings in the Cloudflare dashboard (Worker -> Settings):
//   Variables and Secrets:  NTFY_TOPIC (secret)      your ntfy topic name
//                           MIN_DISCOUNT (text, opt.) e.g. 20 -> only alert for 20%+ off
//   Bindings:               KV namespace named SEEN  (remembers which deals were already alerted)
//   Triggers -> Cron:       */5 * * * *

const SITE = "https://blockbusterdeals.net";
const APP = "https://bigdeals-usa.pages.dev/";
const COUNT = 40;
const UA = "Mozilla/5.0 (Big Deals USA; +" + APP + ")";

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
function decode(s) {
  return String(s || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&([a-z]+);/gi, (m, n) => ENTITIES[n.toLowerCase()] ?? m)
    .replace(/\s+/g, " ")
    .trim();
}

function money(minor, unit) {
  if (minor === null || minor === undefined || minor === "") return null;
  const v = Number(minor) / 10 ** unit;
  return "$" + (Number.isInteger(v) ? v.toLocaleString("en-US") : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
}

function storeFor(url, cats) {
  const host = (() => { try { return new URL(url).host.toLowerCase(); } catch { return ""; } })();
  if (host.includes("amzn") || host.includes("amazon")) return "Amazon";
  for (const [k, name] of [["walmart", "Walmart"], ["target", "Target"], ["hsn", "HSN"], ["qvc", "QVC"], ["macys", "Macy's"]])
    if (host.includes(k)) return name;
  return cats[0] || "Deal";
}

async function getJSON(url) {
  const r = await fetch(url, { headers: { "User-Agent": UA, Accept: "application/json" }, cf: { cacheTtl: 60 } });
  if (!r.ok) throw new Error(url + " -> " + r.status);
  return r.json();
}

async function loadDeals() {
  const [products, dates] = await Promise.all([
    getJSON(`${SITE}/wp-json/wc/store/v1/products?per_page=${COUNT}&orderby=date&order=desc`),
    getJSON(`${SITE}/wp-json/wp/v2/product?per_page=${COUNT}&_fields=id,date_gmt`),
  ]);
  const posted = Object.fromEntries(dates.map(d => [d.id, d.date_gmt]));
  return products.map(p => {
    const pr = p.prices || {};
    const unit = Number(pr.currency_minor_unit ?? 2);
    const price = pr.price, reg = pr.regular_price;
    const off = price && reg && Number(reg) > Number(price) && Number(price) > 0
      ? Math.round(100 * (1 - Number(price) / Number(reg))) : 0;
    const cats = (p.categories || []).map(c => decode(c.name));
    const buy = (p.add_to_cart && p.add_to_cart.url) || p.permalink;
    const img = (p.images || [])[0] || {};
    return {
      id: "bbd-" + p.id,
      store: storeFor(buy, cats),
      title: decode(p.name),
      price: money(price, unit),
      was: off ? money(reg, unit) : null,
      discount: off ? off + "% off" : null,
      save: off ? money(Number(reg) - Number(price), unit) : null,
      code: null,
      notes: null, // the site's own write-up stays on the site (copyright); "page" links to it
      link: buy,
      page: p.permalink,
      image: img.thumbnail || img.src || null,
      category: cats[0] || null,
      postedAt: posted[p.id] ? posted[p.id] + "Z" : null,
      expiresAt: null,
      status: p.is_in_stock === false ? "expired" : "active",
      source: "site",
    };
  });
}

// ---- Black Friday list (Google Sheet), served at /blackfriday until BF_END ----
// The sheet's CSV feed works without sign-in but has no CORS header, so the app reads it through here.
const BF_SHEET = "https://docs.google.com/spreadsheets/d/18zHldCWqzRWQu0c6vmNsXhQXtl9dJgaYHMNDiZEzLh4/gviz/tq?tqx=out:csv";
const BF_END = "2026-12-03T04:59:00Z"; // 11:59 PM US Eastern on Dec 2
// The sheet has no product links, so cards open a search for the item at its store.
const SEARCH = {
  "Amazon": "https://www.amazon.com/s?k=",
  "Best Buy": "https://www.bestbuy.com/site/searchpage.jsp?st=",
  "Macy's": "https://www.macys.com/shop/search?keyword=",
  "Groupon": "https://www.groupon.com/search?query=",
  "Walmart": "https://www.walmart.com/search?q=",
  "Kohl's": "https://www.kohls.com/search.jsp?search=",
  "Home Depot": "https://www.homedepot.com/s/",
  "Michael Kors": "https://www.michaelkors.com/search?q=",
  "Lowe's": "https://www.lowes.com/search?searchTerm=",
  "Woot": "https://www.woot.com/search?query=",
  "Walgreens": "https://www.walgreens.com/search/results.jsp?Ntt=",
  "CVS": "https://www.cvs.com/search?searchTerm=",
  "Target": "https://www.target.com/s?searchTerm=",
  "Samsung": "https://www.samsung.com/us/search/searchMain/?searchTerm=",
};

// gviz CSV quotes every field; unquoted fields are handled too. Regex-based to stay well
// under the free plan's CPU limit for ~1,500 rows.
function parseCSV(text) {
  const rows = []; let row = [];
  const re = /(?:"((?:[^"]|"")*)"|([^,\r\n]*))(,|\r?\n|$)/g;
  let m;
  while ((m = re.exec(text))) {
    row.push(m[1] !== undefined ? m[1].replace(/""/g, '"') : m[2]);
    if (m[3] !== ",") { rows.push(row); row = []; }
    if (m[3] === "") break;
  }
  return rows;
}

function hashId(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

async function loadBlackFriday() {
  const r = await fetch(BF_SHEET, { headers: { "User-Agent": UA }, cf: { cacheTtl: 300, cacheEverything: true } });
  if (!r.ok) throw new Error("sheet -> " + r.status);
  const rows = parseCSV(await r.text());
  const offers = [], ids = new Set();
  let section = "Electronics";
  for (let i = 1; i < rows.length; i++) {           // row 0 is the sheet's heading
    const [title = "", price = "", code = "", store = "", notes = ""] = rows[i].map(c => (c || "").trim());
    if (!title) continue;
    const url = (notes.match(/https?:\/\/[^\s;]+/) || [])[0];
    if (!price && !store && !url) { section = title; continue; } // section heading row
    const was = notes.match(/Was\s+(\$[\d,]+(?:\.\d+)?)\s*\((\d+)% off\)/i);
    const off = was && +was[2] > 0;
    const id = "bf-" + hashId(store + "|" + title + "|" + price);
    if (ids.has(id)) continue; // same item listed twice in the sheet
    ids.add(id);
    const q = encodeURIComponent(title.slice(0, 120));
    offers.push({
      id,
      store: store || "Special deal",
      title,
      price: price || null,
      was: off ? was[1] : null,
      discount: off ? was[2] + "% off" : null,
      save: null,
      code: code || null,
      notes: null,
      link: url || (SEARCH[store] ? SEARCH[store] + q : "https://www.google.com/search?q=" + encodeURIComponent((store + " " + title).slice(0, 150))),
      linkLabel: url ? "Open deal ↗" : "Find at " + (store || "store") + " ↗",
      page: null,
      image: null,
      category: section,
      postedAt: null,
      expiresAt: BF_END,
      status: "active",
      source: "sheet",
      bf: true,
    });
  }
  return offers;
}

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Content-Type": "application/json; charset=utf-8",
};

async function ntfy(topic, msg) {
  await fetch("https://ntfy.sh/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...msg, topic }),
  });
}

async function checkAndNotify(env) {
  if (!env.NTFY_TOPIC || !env.SEEN) return "not configured (needs NTFY_TOPIC secret and SEEN KV binding)";
  const deals = await loadDeals();
  const seenRaw = await env.SEEN.get("ids");
  const seen = new Set(seenRaw ? JSON.parse(seenRaw) : []);
  const firstRun = !seenRaw;
  const min = Number(env.MIN_DISCOUNT || 0);
  const fresh = firstRun ? [] : deals.filter(d => !seen.has(d.id) && (parseInt(d.discount) || 0) >= min);

  if (fresh.length > 4) {
    await ntfy(env.NTFY_TOPIC, {
      title: `${fresh.length} new deals`,
      tags: ["shopping_cart"],
      click: APP,
      message: fresh.slice(0, 8).map(d => [d.price, d.discount, d.title.slice(0, 55)].filter(Boolean).join(" · ")).join("\n"),
    });
  } else {
    for (const d of fresh) {
      const head = [d.price, d.discount].filter(Boolean).join(" · ");
      await ntfy(env.NTFY_TOPIC, {
        title: (head ? head + " — " : "") + d.title.slice(0, 80),
        message: [d.store, d.was ? "was " + d.was : null, d.save ? "you save " + d.save : null].filter(Boolean).join(" · ") || "New deal",
        tags: ["shopping_cart"],
        click: d.link || APP,
        attach: d.image || undefined,
        actions: [{ action: "view", label: "Open app", url: APP }],
      });
    }
  }
  // Remember everything we've seen (bounded list).
  const ids = [...deals.map(d => d.id), ...seen].filter((v, i, a) => a.indexOf(v) === i).slice(0, 500);
  await env.SEEN.put("ids", JSON.stringify(ids));
  return firstRun ? `first run: remembered ${deals.length} deals, no alerts` : `alerted ${fresh.length}`;
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    const url = new URL(request.url);
    try {
      if (url.pathname === "/check") {
        // Manual test: runs the same check the cron does.
        return new Response(JSON.stringify({ result: await checkAndNotify(env) }), { headers: CORS });
      }
      const cache = caches.default;
      if (url.pathname === "/blackfriday") {
        if (Date.now() > Date.parse(BF_END))
          return new Response(JSON.stringify({ ended: true, endsAt: BF_END, offers: [] }), { headers: CORS });
        const bfKey = new Request(url.origin + "/bf-v1");
        let bfRes = await cache.match(bfKey);
        if (!bfRes) {
          const offers = await loadBlackFriday();
          bfRes = new Response(JSON.stringify({ fetchedAt: new Date().toISOString(), endsAt: BF_END, offers }), {
            headers: { ...CORS, "Cache-Control": "public, max-age=300" },
          });
          ctx.waitUntil(cache.put(bfKey, bfRes.clone()));
        }
        return bfRes;
      }
      const key = new Request(url.origin + "/deals-v1");
      let res = await cache.match(key);
      if (!res) {
        const offers = await loadDeals();
        res = new Response(JSON.stringify({ source: SITE, fetchedAt: new Date().toISOString(), offers }), {
          headers: { ...CORS, "Cache-Control": "public, max-age=120" },
        });
        ctx.waitUntil(cache.put(key, res.clone()));
      }
      return res;
    } catch (e) {
      return new Response(JSON.stringify({ error: String(e.message || e) }), { status: 502, headers: CORS });
    }
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(checkAndNotify(env).then(r => console.log(r)).catch(e => console.log("check failed:", e)));
  },
};
