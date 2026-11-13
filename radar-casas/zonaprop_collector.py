#!/usr/bin/env python3
"""Read public Zonaprop residential rental search pages into the Radar CABA.

This is a normal HTML reader: no login, hidden API, CAPTCHA solver, proxies,
browser-fingerprint evasion, or attempts to bypass HTTP 403. Source failures are
reported explicitly and never cause records to be marked inactive.
"""
import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
import requests
from bs4 import BeautifulSoup

SOURCE = "Zonaprop"
ORIGIN = "https://www.zonaprop.com.ar"
NEIGHBORHOODS = {
    "Liniers": "liniers",
    "Mataderos": "mataderos",
    "Villa Luro": "villa-luro",
    "Versalles": "versalles",
    "Vélez Sarsfield": "velez-sarsfield",
    "Villa Devoto": "villa-devoto",
    "Monte Castro": "monte-castro",
}
KINDS = {"casas": "Casa", "ph": "PH", "departamentos": "Departamento"}
LINK_RE = re.compile(r"/propiedades/clasificado/[^?#]+?-(\d{7,9})\.html", re.I)
PRICE_RE = re.compile(r"(?<![A-Za-z])(?:USD|U\$S|US\$|ARS|\$)\s*(?:\$\s*)?(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{3,9})", re.I)
AREA_RE = re.compile(r"\b(\d{2,4})\s*m(?:²|2)\s*(?:tot\.?|total(?:es)?)?", re.I)
BEDS_RE = re.compile(r"\b(\d{1,2})\s*dorm(?:itorios?)?\.?\b", re.I)
ROOMS_RE = re.compile(r"\b(\d{1,2})\s*amb(?:ientes?)?\.?\b", re.I)
BAD_TITLE = re.compile(r"captcha|just a moment|access denied|verifying your browser", re.I)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RadarCABA/1.0; public property listings)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-AR,es;q=0.9",
}
# Do not crawl paginated paths disallowed in robots.txt. Only first pages for
# each bairro/type, which are allowed and enough to discover the newest subset.

def category_urls(names=None, kinds=None):
    neighborhoods = names or list(NEIGHBORHOODS)
    kinds = kinds or list(KINDS)
    for name in neighborhoods:
        for kind in kinds:
            yield name, kind, f"{ORIGIN}/{kind}-alquiler-{NEIGHBORHOODS[name]}.html"


def canonical(href):
    try:
        url = urljoin(ORIGIN, href)
        p = urlsplit(url)
        if p.scheme != "https" or p.hostname not in ("www.zonaprop.com.ar", "zonaprop.com.ar"):
            return None, None
        match = LINK_RE.search(p.path)
        if not match:
            return None, None
        # Eliminate tracking query strings (including robots-disallowed n_src).
        return urlunsplit(("https", "www.zonaprop.com.ar", p.path, "", "")), "zp-" + match.group(1)
    except (ValueError, TypeError):
        return None, None


def cards(soup):
    found = {}
    for a in soup.select('a[href*="/propiedades/clasificado/"]'):
        url, record_id = canonical(a.get("href", ""))
        if not url or record_id in found:
            continue
        card = None
        for parent in a.parents:
            if not hasattr(parent, "select"):
                break
            distinct = set()
            for link in parent.select('a[href*="/propiedades/clasificado/"]'):
                other, oid = canonical(link.get("href"))
                if other:
                    distinct.add(oid)
                if len(distinct) > 1:
                    break
            if len(distinct) > 1:
                break
            text = parent.get_text(" ", strip=True)
            # A complete card has a price, beds/rooms/area, and an image or
            # a heading; the plain description link alone is insufficient.
            if len(text) >= 45 and len(text) <= 6500 and PRICE_RE.search(text) and (
                ROOMS_RE.search(text) or BEDS_RE.search(text) or AREA_RE.search(text)
            ):
                card = parent
                if parent.select_one('img[src*="zonapropcdn.com"],img[data-src*="zonapropcdn.com"],[data-qa*="PRICE"]'):
                    break
        if card is not None:
            found[record_id] = (url, card)
    return found


def number(raw):
    # Rent amounts in cards are integer amounts with thousands separators.
    raw = raw.replace(" ", "").strip()
    if raw.count(".") or raw.count(","):
        raw = re.sub(r"[.,]", "", raw)
    try:
        return int(raw)
    except ValueError:
        return 0


def extract_price(text):
    match = PRICE_RE.search(text)
    if not match:
        return None, None
    currency_label = match.group(0)[:match.group(0).find(match.group(1))].upper()
    currency = "USD" if any(mark in currency_label for mark in ("USD", "US$", "U$S")) else "ARS"
    price = number(match.group(1))
    bounds = (250, 25000) if currency == "USD" else (100000, 100000000)
    return (price, currency) if bounds[0] <= price <= bounds[1] else (None, None)


def visible_image(card):
    for img in card.select("img"):
        urls = [img.get("data-src", ""), img.get("src", "")]
        srcset = img.get("srcset") or img.get("data-srcset") or ""
        urls.extend(part.split()[0] for part in srcset.split(",") if part.strip())
        for src in urls:
            full = urljoin(ORIGIN, src)
            if urlsplit(full).hostname == "imgar.zonapropcdn.com" and "/avisos/" in urlsplit(full).path:
                return full
    return None


# Zonaprop sometimes appends "also in nearby cities" recommendations to a
# neighborhood result page. Validate each card's actual location, not the
# catalog URL, before calling it a CABA listing.
WRONG_MARKET = re.compile(
    r"\b(?:Mor[oó]n|Lomas del Mirador|La Matanza|Ramos Mej[ií]a|Ciudadela|"
    r"San Justo|Tapiales|Villa Madero|Isidro Casanova|"
    r"Haedo|Castelar|Ituzaing[oó]|Gonz[aá]lez Cat[aá]n|Rafael Castillo)\b", re.I
)
CABA_OUTSIDE_SCOPE = re.compile(
    r"\b(?:Parque Avellaneda|Floresta|Flores|Villa Lugano|"
    r"Villa Soldati|Caballito|Villa del Parque|Villa Real|Parque Chacabuco)\b", re.I
)

def listing_location(card):
    node = card.select_one('[data-qa="POSTING_CARD_LOCATION"],[class*="postingLocations-module__location-text"]')
    return node.get_text(" ", strip=True) if node else ""

def inferred_bairro(location, requested):
    if not location or WRONG_MARKET.search(location) or CABA_OUTSIDE_SCOPE.search(location):
        return None
    for name in sorted(NEIGHBORHOODS, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", location, re.I):
            return name
    # A street-only result is still valid when the category is explicitly scoped.
    return requested

def extract_address(card, text, bairro):
    for selector in ('[data-qa*="LOCATION"]', '[class*="posting-location"]', '[class*="postingLocation"]',
                     '[class*="postingCard-module__posting-address"]', '[class*="postingCard-module__posting-location"]'):
        for node in card.select(selector):
            val = node.get_text(" ", strip=True)
            if 5 <= len(val) < 120 and not re.search(r"\b(?:Capital Federal|CABA)\b", val, re.I):
                return val + ", " + bairro + ", CABA"
    # If only the bairro is verifiable, do not invent a street address.
    return bairro + ", CABA"


def advertiser(card):
    for sel in ('[data-qa*="PUBLISHER_NAME"]', '[data-qa*="POSTING_CARD_PUBLISHER"]',
                'a[href*="/inmobiliarias/"]', '[class*="publisher-name"]'):
        for node in card.select(sel):
            val = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
            if 3 <= len(val) <= 100 and "logo" not in val.lower():
                return val
    if "dueño directo" in card.get_text(" ", strip=True).lower():
        return "Dueño directo"
    return "Anunciante não identificado"


def parsed_card(url, id_, card, bairro, kind):
    full_text = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
    actual_bairro = inferred_bairro(listing_location(card), bairro)
    if not actual_bairro:
        return None
    bairro = actual_bairro
    price, cur = extract_price(full_text)
    if price is None:
        return None
    # Use features next to the particular card, not suggested listings or
    # arbitrary numerals in a long prose description.
    features_node = card.select_one('[data-qa="POSTING_CARD_FEATURES"]')
    features = features_node.get_text(" ", strip=True) if features_node else full_text[:260]
    room_match = ROOMS_RE.search(features)
    bed_match = BEDS_RE.search(features)
    rooms = int(room_match.group(1)) if room_match else 0
    beds = int(bed_match.group(1)) if bed_match else 0
    # Only parse 3+ ambientes or 2+ bedrooms (default UI still filters
    # to 4 ambientes / 3 bedrooms). Never infer a room from a random number.
    if rooms < 3 and beds < 2:
        return None
    area_match = AREA_RE.search(features)
    area = int(area_match.group(1)) if area_match else None
    if area is not None and area < 60:
        return None
    desc_element = card.select_one('[data-qa="POSTING_CARD_DESCRIPTION"],[class*="posting-description"]')
    description = (desc_element.get_text(" ", strip=True) if desc_element else full_text)
    description = re.sub(r"\s+", " ", description).strip()[:1200]
    if not description:
        return None
    # Recommendations sometimes appear on the result page with a misleading
    # search-category location. Prefer a clear property description that names
    # another neighborhood/city or says commercial-only.
    first_desc = description[:360]
    if re.search(r"(?:alquiler\s+comercial\s+exclusivamente|uso\s+comercial\s+exclusivo|exclusivamente\s+comercial)",first_desc,re.I):
        return None
    if re.search(r"(?:\ben\s+(?:el\s+)?(?:barrio\s+de\s+)?|\bubicad[ao]\s+en\s+)(?:Villa\s+Lugano|Parque\s+Avellaneda|Mor[oó]n|Lomas\s+del\s+Mirador)\b",first_desc,re.I):
        return None
    for real_bairro in sorted(NEIGHBORHOODS,key=len,reverse=True):
        if re.search(r"(?:\ben\s+(?:el\s+)?(?:barrio\s+de\s+)?|\bubicad[ao]\s+en\s+)" + re.escape(real_bairro) + r"\b", first_desc, re.I):
            bairro=real_bairro
            break
    title = f"{KINDS[kind]} em aluguel · {rooms or '?'} ambientes · {bairro}"
    photo = visible_image(card)
    # Never assign neighboring carousel images to this property.
    tipo = "PH" if "alclph" in url else ("Casa" if "alclca" in url else KINDS[kind])
    if tipo not in KINDS.values():
        tipo = KINDS[kind]
    return {
        "id": id_, "source": SOURCE, "mode": "aluguel", "bairro": bairro,
        "address": extract_address(card, full_text, bairro),
        "tipo": tipo, "price": price, "cur": cur, "beds": beds, "area": area,
        "patio": bool(re.search(r"\bpatio\b|\bterraza\b|\bjard[ií]n\b", description, re.I)),
        "garage": bool(re.search(r"\bcochera\b|\bgarage\b|\bgaraje\b", description, re.I)),
        "agency": advertiser(card), "url": url,
        "photo": photo, "photos": [photo] if photo else [],
        "detail": title + " — " + description,
        "tag": "Zonaprop", "verified": "Publicado no Zonaprop; disponibilidade a confirmar",
    }


def fetch(session, url):
    try:
        r = session.get(url, headers=HEADERS, timeout=(7, 19), allow_redirects=True)
    except requests.RequestException as exc:
        return None, "connection: " + str(exc)[:100]
    if r.status_code != 200:
        return None, "HTTP " + str(r.status_code)
    if len(r.content) > 4_000_000:
        return None, "page-too-large"
    soup = BeautifulSoup(r.content, "html.parser")
    if BAD_TITLE.search(soup.title.get_text(" ", strip=True) if soup.title else ""):
        return None, "challenge"
    return soup, None


def photos_by_id(soup):
    """Return distinct gallery URLs per ad ID, never photos from another listing."""
    result = {}
    seen = {}
    raw = str(soup).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/").replace("&amp;", "&")
    for match in re.finditer(r"https://imgar\.zonapropcdn\.com/avisos/[^\"'<>\s\\]+", raw, re.I):
        url = match.group(0).rstrip("),;").split("&quot;")[0]
        path = urlsplit(url).path
        group = re.search(r"/(?:\d{2}/){4,5}", path)
        if not group or not re.search(r"\.(?:jpe?g|webp|png)$", path, re.I):
            continue
        listing_id = "".join(re.findall(r"\d{2}", group.group(0))[-4:])
        if len(listing_id) != 8:
            continue
        filename = path.rsplit("/", 1)[-1]
        seen.setdefault(listing_id, set())
        if filename in seen[listing_id] or len(result.get(listing_id, [])) >= 16:
            continue
        result.setdefault(listing_id, []).append(url)
        seen[listing_id].add(filename)
    return result


def add_gallery(row, urls):
    """Add photos belonging only to this Zonaprop ID, deduplicated by image file."""
    own_id = row["id"][3:].zfill(8)
    directory = "/"+"/".join(own_id[i:i+2] for i in range(0, 8, 2))+"/"
    merged = []
    seen = set()
    for u in row.get("photos", []) + list(urls):
        try:
            parsed = urlsplit(u)
        except (TypeError, ValueError):
            continue
        if (parsed.scheme != "https" or parsed.hostname != "imgar.zonapropcdn.com"
                or directory not in parsed.path or not re.search(r"\.(?:jpe?g|webp|png)$", parsed.path, re.I)):
            continue
        filename = parsed.path.rsplit("/", 1)[-1]
        if filename in seen:
            continue
        seen.add(filename)
        merged.append(u)
        if len(merged) >= 16:
            break
    row["photos"] = merged
    row["photo"] = merged[0] if merged else None
    return row

def listing_count(soup, kind):
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    label = {"casas":"Casas", "ph":"PH", "departamentos":"Departamentos"}[kind]
    matched = re.search(r"(\d[\d.]*)\s+" + label + r"\s+en\s+alquiler", title, re.I)
    return int(matched.group(1).replace(".","")) if matched else None

def run(names, kinds, limit, delay, stop_on_block=True, detail_gallery_max=2):
    items, ids = {}, set()
    checked = reached = links = 0
    failures = []
    detail_checks = 0
    more_photos = 0
    details_blocked = False
    with requests.Session() as session:
        for name, kind, cat_url in category_urls(names, kinds):
            if limit and checked >= limit:
                break
            checked += 1
            soup, err = fetch(session, cat_url)
            if err:
                failures.append({"category": cat_url, "reason": err})
                print(json.dumps({"category": cat_url, "status": err}, ensure_ascii=False), flush=True)
                if stop_on_block and (err in ("HTTP 403", "HTTP 429", "challenge")):
                    print(json.dumps({"notice": "Source throttled or blocked; stopping without bypassing access controls"}), flush=True)
                    break
                time.sleep(delay)
                continue
            reached += 1
            sample = cards(soup)
            advertised = listing_count(soup, kind)
            # The HTML often contains 30 cards even if the header says just
            # 4-8 matching properties: the rest are recommendations elsewhere.
            if advertised is not None:
                sample = dict(list(sample.items())[:min(advertised,30)])
            available_photos = photos_by_id(soup)
            links += len(sample)
            added = 0
            for id_, (url, card) in sample.items():
                if id_ in ids:
                    continue
                row = parsed_card(url, id_, card, name, kind)
                if row:
                    add_gallery(row, available_photos.get(id_[3:].zfill(8), []))
                    ids.add(id_)
                    items[id_] = row
                    added += 1
            # A search card often contains only a thumbnail. Fetch a small,
            # rotating sample of exact detail pages to add the *real* gallery
            # images. Stop on any portal block, without trying to evade it.
            if detail_gallery_max and not details_blocked:
                current = [items[k] for k in sample if k in items]
                if current:
                    start = (datetime.date.today().toordinal() * max(1, detail_gallery_max)) % len(current)
                    for offset in range(min(detail_gallery_max, len(current))):
                        row = current[(start + offset) % len(current)]
                        if len(row["photos"]) >= 8:
                            continue
                        details, detail_error = fetch(session, row["url"])
                        detail_checks += 1
                        if detail_error:
                            if detail_error in ("HTTP 403", "HTTP 429", "challenge"):
                                details_blocked = True
                                print(json.dumps({"gallery": "blocked", "reason": detail_error,
                                                  "stopping_detail_requests": True}), flush=True)
                                break
                            continue
                        before = len(row["photos"])
                        add_gallery(row, photos_by_id(details).get(row["id"][3:].zfill(8), []))
                        more_photos += max(0, len(row["photos"]) - before)
                        time.sleep(delay)
            print(json.dumps({"category": cat_url, "status": "HTTP 200", "linked_cards": len(sample), "relevant": added}, ensure_ascii=False), flush=True)
            time.sleep(delay)
    status = ("ok" if reached == checked and reached > 0 and len(items) > 0 else
              "partial" if reached > 0 and len(items)>0 else
              "blocked" if failures and any(f["reason"] in ("HTTP 403","HTTP 429","challenge") for f in failures) else
              "no_results" if reached else "unavailable")
    return list(items.values()), {
        "source": SOURCE, "status": status, "pages_checked": checked,
        "pages_reached": reached, "listing_links": links, "listings_parsed": len(items),
        "detail_pages_checked": detail_checks, "extra_gallery_photos": more_photos,
        "last_error": failures[0]["reason"] if failures else None
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-path", required=True)
    parser.add_argument("--max-pages", type=int, default=21)
    parser.add_argument("--neighborhood", choices=list(NEIGHBORHOODS), action="append")
    parser.add_argument("--type", choices=list(KINDS), action="append")
    parser.add_argument("--delay", type=float, default=1.35)
    parser.add_argument("--detail-gallery-max", type=int, default=2, help="max property detail gallery lookups per catalog, stop when blocked")
    args = parser.parse_args()
    listings, report = run(args.neighborhood, args.type, max(0, args.max_pages), max(.7, args.delay), detail_gallery_max=max(0,min(4,args.detail_gallery_max)))
    path = Path(args.export_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"kind": "upsert", "sources": [SOURCE], "listings": listings,
                                "portal_status": report}, ensure_ascii=False), encoding="utf-8")
    print("ZONAPROP_SUMMARY " + json.dumps(report, ensure_ascii=False), flush=True)
    for item in listings[:4]:
        print("ZONAPROP_SAMPLE " + json.dumps({k:item.get(k) for k in ("id","agency","bairro","address","tipo","price","cur","beds","area","photo","url")}, ensure_ascii=False),flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
