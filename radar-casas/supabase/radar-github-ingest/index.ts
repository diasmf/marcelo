// GitHub OIDC authenticated ingest. The Supabase admin key never leaves this Edge Function.
const PROJECT = "qfuflpvxcgvivsihlkwb";
const REPO = "diasmf/marcelo";
const REPO_ID = "253567197";
const WORKFLOW = REPO + "/.github/workflows/radar-collector.yml@refs/heads/master";
const AUDIENCE = "radar-caba-ingest";
const OIDC_ISSUER = "https://token.actions.githubusercontent.com";
const JWKS_URL = OIDC_ISSUER + "/.well-known/jwks";
const reply = (body: unknown, status = 200) => Response.json(body, {status, headers: {"cache-control": "no-store"}});
const base64url = (s: string) => {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const bytes = atob(b64 + "=".repeat((4 - b64.length % 4) % 4));
  return Uint8Array.from(bytes, ch => ch.charCodeAt(0));
};
const decode = (s: string) => JSON.parse(new TextDecoder().decode(base64url(s)));
function host(raw: string) {
  try {
    const u = new URL(raw);
    return u.protocol === "https:" ? u.hostname.toLowerCase().replace(/^www\./, "") : "";
  } catch { return ""; }
}
async function verifyGitHubOIDC(authHeader: string) {
  if (!authHeader.startsWith("Bearer ")) throw Error("Missing GitHub identity");
  const jwt = authHeader.slice(7);
  if (jwt.length > 8192) throw Error("Identity length");
  const parts = jwt.split(".");
  if (parts.length !== 3) throw Error("Invalid JWT structure");
  const header = decode(parts[0]);
  if (header.alg !== "RS256" || typeof header.kid !== "string") throw Error("Unexpected JWT algorithm");
  const response = await fetch(JWKS_URL, { signal: AbortSignal.timeout(7000), headers: {"accept": "application/json"} });
  if (!response.ok) throw Error("Identity keys temporarily unavailable");
  const keySet = await response.json();
  const jwk = keySet.keys?.find((x: Record<string, unknown>) => x.kid === header.kid && x.kty === "RSA" && (!x.use || x.use === "sig"));
  if (!jwk) throw Error("Unrecognized GitHub signing key");
  const key = await crypto.subtle.importKey("jwk", jwk, {name: "RSASSA-PKCS1-v1_5", hash: "SHA-256"}, false, ["verify"]);
  const signed = new TextEncoder().encode(parts[0] + "." + parts[1]);
  const valid = await crypto.subtle.verify({name: "RSASSA-PKCS1-v1_5"}, key, base64url(parts[2]), signed);
  if (!valid) throw Error("Invalid signature");
  const c = decode(parts[1]);
  const now = Math.floor(Date.now() / 1000);
  if (c.iss !== OIDC_ISSUER || c.aud !== AUDIENCE || c.exp < now - 10 || c.nbf > now + 10 || c.iat > now + 10) throw Error("Expired or wrong audience");
  if (c.iat < now - 600 || c.exp > now + 900) throw Error("Unexpected token validity window");
  if (c.repository !== REPO || c.repository_id !== REPO_ID || c.repository_owner !== "diasmf" || c.ref !== "refs/heads/master") throw Error("Wrong GitHub repository or branch");
  if (c.workflow_ref !== WORKFLOW || !["schedule", "workflow_dispatch", "push"].includes(c.event_name)) throw Error("Wrong workflow or trigger");
  return {repository: c.repository, event: c.event_name, run_id: String(c.run_id || "")};
}
function admin() {
  const url = Deno.env.get("SUPABASE_URL");
  const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
  const key = keys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !key) throw Error("Supabase server key unavailable");
  return { url, key };
}
async function db(table: string, method: string, params: Record<string,string> | null, body: unknown = null) {
  const {url, key} = admin();
  const query = new URLSearchParams(params || {});
  const endpoint = url + "/rest/v1/" + table + (params ? "?" + query.toString() : "");
  const res = await fetch(endpoint, {
    method, headers: {
      "apikey": key, "authorization": "Bearer " + key,
      "content-type": "application/json", "prefer": "return=minimal"
    }, body: body === null ? undefined : JSON.stringify(body)
  });
  if (!res.ok) {
    console.error("Database error", table, method, res.status, (await res.text()).slice(0,250));
    throw Error("Database " + res.status);
  }
  return method === "GET" ? res.json() : null;
}
type Incoming = Record<string, unknown>;
function clean(x: Incoming, sourceHost: string) {
  if (typeof x.url !== "string" || host(x.url) !== sourceHost || x.url.length > 900) throw Error("wrong-source-URL");
  if (!/^agency-[a-f0-9]{20}$/.test(String(x.id || ""))) throw Error("invalid-ID");
  if (x.mode !== "aluguel" || x.cur !== "ARS" || !["Casa","PH","Departamento"].includes(String(x.tipo))) throw Error("invalid-listing");
  if (!["Liniers","Mataderos","Villa Luro","Versalles","Vélez Sarsfield","Villa Devoto","Monte Castro"].includes(String(x.bairro))) throw Error("outside-neighborhood");
  const price = Number(x.price);
  if (!Number.isFinite(price) || price < 100000 || price > 100000000) throw Error("invalid-price");
  const area = x.area == null ? null : Number(x.area);
  if (area != null && (!Number.isFinite(area) || area < 60 || area > 10000)) throw Error("invalid-area");
  const beds = Number(x.beds);
  if (!Number.isSafeInteger(beds) || beds < 0 || beds > 12) throw Error("invalid-beds");
  const photos = Array.isArray(x.photos) ? [...new Set(x.photos.filter((p: unknown) => typeof p === "string" && /^https:\/\//i.test(p) && p.length < 1000))].slice(0,20) : [];
  return {
    id: String(x.id), url: String(x.url), agency: String(x.agency).slice(0,120), mode: "aluguel",
    bairro: String(x.bairro), tipo: String(x.tipo),
    address: String(x.address || String(x.bairro) + ", CABA").slice(0,250),
    price, cur: "ARS", beds, area,
    patio: x.patio === true, garage: x.garage === true,
    photo: photos[0] || null, photos,
    detail: String(x.detail || "").slice(0,1800),
    tag: "Novo no Radar", verified: "Fonte própria; disponibilidade a confirmar",
    listing_status: "pending"
  };
}
async function findExisting(url: string) {
  const lookup = async (u: string) => await db("radar_caba_listings", "GET", {select:"id,listing_status,photos,photo,address", url: "eq." + u, limit:"1"}) as Record<string,unknown>[];
  const exact = await lookup(url);
  if (exact.length) return exact[0];
  const alternate = url.endsWith("/") ? url.replace(/\/$/, "") : url + "/";
  const other = await lookup(alternate);
  return other[0] || null;
}
async function ingest(rows: Incoming[], sourceNames: string[]) {
  if (rows.length > 200) return reply({error: "batch-too-large"}, 413);
  const catalog = await db("radar_caba_agencies", "GET", {select:"name,url"}) as {name:string,url:string|null}[];
  const allowed = new Map(catalog.filter(x=>x.url).map(x=>[x.name,host(x.url || "")]));
  let inserted=0, updated=0, rejected=0;
  const errors: Record<string,number> = {};
  for (const input of rows) {
    try {
      if (!input || typeof input !== "object" || typeof input.agency !== "string") throw Error("bad-payload");
      if (!sourceNames.includes(input.agency)) throw Error("not-in-shard");
      const agencyHost = allowed.get(input.agency);
      if (!agencyHost) throw Error("agency-not-registered");
      const row = clean(input, agencyHost);
      const now = new Date().toISOString();
      const existing = await findExisting(row.url);
      if (existing) {
        const changes: Record<string,unknown> = {
          updated_at: now, status_checked_at: now, price: row.price,
        };
        if (row.area !== null) changes.area = row.area;
        if (Number(row.beds) > 0) changes.beds = row.beds;
        // Preserve manually curated addresses and photographs.
        if (!existing.photo && row.photo) { changes.photo = row.photo; changes.photos = row.photos; }
        if (existing.listing_status === "inactive") {
          changes.listing_status = "pending";
          changes.status_reason = "Seen on originating agency site";
        }
        await db("radar_caba_listings", "PATCH", {id:"eq."+String(existing.id)}, changes);
        updated++;
      } else {
        await db("radar_caba_listings", "POST", null, {...row, updated_at: now, status_checked_at: now});
        inserted++;
      }
    } catch (e) {
      rejected++;
      const reason = e instanceof Error ? e.message.slice(0,80) : "unknown";
      errors[reason] = (errors[reason] || 0) + 1;
    }
  }
  return reply({ok: rejected===0, inserted, updated, rejected, errors, sources: sourceNames.length}, rejected ? 422 : 200);
}
Deno.serve(async req => {
  if (req.method !== "POST") return reply({error:"method-not-allowed"},405);
  const length = Number(req.headers.get("content-length") || "0");
  if (length > 900000) return reply({error:"body-too-large"},413);
  try {
    const identity = await verifyGitHubOIDC(req.headers.get("authorization") || "");
    const text = await req.text();
    if (text.length > 900000) return reply({error:"body-too-large"},413);
    const data = JSON.parse(text);
    if (data.kind === "probe") return reply({ok:true, auth:"github-oidc", repository:identity.repository, run_id:identity.run_id});
    if (data.kind !== "upsert" || !Array.isArray(data.listings) || !Array.isArray(data.sources) || data.sources.length > 20) return reply({error:"invalid-request"},400);
    if (!data.sources.every((s:unknown)=>typeof s==="string"&&s.length<130)) return reply({error:"invalid-sources"},400);
    return await ingest(data.listings, data.sources);
  } catch (e) {
    const message = e instanceof Error ? e.message : "unknown";
    if (/GitHub|identity|signature|token|JWT|audience|repository|workflow|trigger|Expired|Unrecognized|validity/i.test(message)) return reply({error:"unauthorized"},401);
    console.error("Ingest error:", message.slice(0,180));
    return reply({error:"unavailable"},503);
  }
});
