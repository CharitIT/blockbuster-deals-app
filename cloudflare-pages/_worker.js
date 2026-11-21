// Serves the app at https://usa-blockbuster-deals.pages.dev/ by forwarding each request to
// GitHub Pages, so whatever is pushed to GitHub (including the deals bot) shows up here
// right away, with no Cloudflare rebuild.
// Deploy (from a folder holding only this file, or Wrangler may upload more):
//   npx wrangler pages deploy <folder> --project-name usa-blockbuster-deals --branch main --force
// --force keeps it on classic Pages (pages.dev); without it Wrangler makes a workers.dev Worker instead.
const ORIGIN = "https://charitit.github.io/blockbuster-deals-app";

export default {
  async fetch(request) {
    if (request.method !== "GET" && request.method !== "HEAD")
      return new Response("Method not allowed", { status: 405 });
    const url = new URL(request.url);
    const res = await fetch(ORIGIN + url.pathname + url.search, {
      method: request.method,
      redirect: "manual",
      headers: { Accept: request.headers.get("Accept") || "*/*" },
    });
    const headers = new Headers(res.headers);
    // Keep GitHub's own redirects (e.g. adding a trailing slash) on this domain.
    const loc = headers.get("Location");
    if (loc && loc.startsWith(ORIGIN)) headers.set("Location", loc.slice(ORIGIN.length) || "/");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  },
};
