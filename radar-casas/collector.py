#!/usr/bin/env python3
"""Radar CABA: conservative property collector for agency-owned websites.

Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY for writes.
Dry-run by default; --apply writes only new, individually eligible listings.
Never changes feedback and never marks a listing inactive on a fetch error.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

NEIGHBORHOODS = ["Liniers", "Mataderos", "Villa Luro", "Versalles", "Vélez Sarsfield", "Villa Devoto", "Monte Castro"]
SOURCES = {
    "Inmobiliaria Falco": "https://www.inmofalco.com.ar/",
    "Grillo e Hijos": "https://inmobiliariagrillo.com.ar/",
    "El Altillo Inmuebles": "https://www.elaltilloinmuebles.com.ar/",
    "Cantale Propiedades": "https://cantalepropiedades.com.ar/",
    "Ricardo López Propiedades": "https://rlpropiedades.com.ar/",
    "Heiber Osornio": "https://www.estudioheiberosornio.com/",
    "Maccaroni": "https://www.maccaroni.com.ar/",
    "Mario Notti Propiedades": "https://marionotti.com.ar/",
    "Millán y Alessi": "https://www.millanalessi.com.ar/",
    "Bener": "https://www.bener.com.ar/",
    "AMI Propiedades": "https://amipropiedades.com.ar/",
    "Furia Propiedades": "https://www.furiapropiedades.com.ar/",
    "Jorge Reale": "https://www.jorgereale.com/",
    "MG Bienes Raíces": "https://bienesraicesmg.com.ar/",
    "Vitale Feola Propiedades": "https://vitalefeola.com.ar/",
    "Acosta": "https://www.acostainmobiliaria.com.ar/",
    "Borrajo": "https://www.borrajopropiedades.com.ar/",
    "Bosich": "https://www.bosichbienesraices.com.ar/",
    "CLOM": "https://www.clompropiedades.com.ar/",
    "Florencio González": "https://florenciogonzalez.com.ar/",
    "Gabriel Figueroa": "https://gabrielfigueroa.com.ar/",
    "Giacoletto": "https://www.giacolettopropiedades.com/",
    "Nolé Propiedades": "https://www.nolepropiedades.com.ar/",
    "Varela Villalba": "https://www.varelavillalba.com.ar/",
    "Jorge Parajon Propiedades": "https://www.parajonpropiedades.com.ar/",
    "Braña Inmobiliaria": "https://xn--abraa-rta.com.ar/",
    "Pallarols Santander Propiedades": "https://www.pallarols-santander.com/",
    "D’Amato Propiedades": "https://www.damatopropiedades.com.ar/",
    "Leonela Cullari Propiedades": "https://www.leonelacullaripropiedades.com/",
    "Magnacca Patelli Propiedades": "https://magnaccapatelli.com/",
}
PROPERTY_PATH = re.compile(r"/(?:propiedad(?:es)?/[^/?#]+|(?:casa|ph|departamento|duplex|triplex)[^/?#]*/[^/?#]+|(?:ph|casa|departamento)-alquiler-[^/?#]+/[^/?#]+|inmueble/[^/?#]+|ficha-[^/?#]+|(?:casa|ph|departamento)-en-(?:alquiler|venta)[^/?#]*ficha-[^/?#]+)", re.I)
RENT = re.compile(r"\b(?:alquiler|alquila|en alquiler)\b", re.I)
SOLD = re.compile(r"\b(?:alquilado|alquilada|reservado|reservada|vendido|vendida|no disponible|suspendido|suspendida)\b", re.I)
SALE_ONLY = re.compile(r"\b(?:en venta|venta de|se vende)\b", re.I)
ROOMS = re.compile(r"(?<!\d)(\d{1,2})\s*(?:ambientes?|amb\b)", re.I)
BEDS = re.compile(r"(?<!\d)(\d{1,2})\s*(?:dormitorios?|habitaciones?)\b", re.I)
AREA = re.compile(r"(?:superficie\s*(?:total|cubierta)?|sup\.?\s*(?:total|cubierta)?|área\s*(?:total|cubierta)?)[^\d]{0,18}(\d{2,4}(?:[,.]\d{1,2})?)\s*(?:m2|m²)?", re.I)
PRICES = re.compile(r"(?:\$\s*|ARS\s*)(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|\d{5,9})", re.I)
STREET = re.compile(r"([A-ZÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ.]+(?:\s+[\wáéíóúñÁÉÍÓÚÑ.]+){0,4})\s+(\d{2,5})\b")
HEADERS = {"User-Agent": "RadarCABA/1.0 (+public listing index; limited requests)", "Accept": "text/html,application/xml;q=0.9,*/*;q=0.5"}


def clean_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", "", ""))


def fetch(session, url):
    try:
        r = session.get(url, headers=HEADERS, timeout=14, allow_redirects=True)
        if r.status_code != 200 or len(r.content) > 3_000_000:
            return ""
        if not any(t in r.headers.get("content-type", "").lower() for t in ("html", "xml", "text/plain")):
            return ""
        return r.text
    except requests.RequestException:
        return ""


def same_host(a, b):
    return bool(a and b and a.lower().removeprefix('www.') == b.lower().removeprefix('www.'))


def candidates(session, base, limit=50):
    host = urlsplit(base).hostname
    found = set()
    for path in ("sitemap_index.xml", "sitemap.xml", "wp-sitemap.xml"):
        xml = fetch(session, urljoin(base, "/" + path))
        if not xml:
            continue
        try:
            root = ET.fromstring(xml)
            links = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
            indexes = [x for x in links if x.endswith(".xml") and same_host(urlsplit(x).hostname, host)][:5]
            for index in indexes:
                inner = fetch(session, index)
                if inner:
                    tree = ET.fromstring(inner)
                    links.extend(el.text.strip() for el in tree.iter() if el.tag.endswith("loc") and el.text)
            found.update(clean_url(x) for x in links if same_host(urlsplit(x).hostname, host) and PROPERTY_PATH.search(urlsplit(x).path))
        except ET.ParseError:
            pass
    html = fetch(session, base)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            url = urljoin(base, a["href"])
            if same_host(urlsplit(url).hostname, host) and PROPERTY_PATH.search(urlsplit(url).path):
                found.add(clean_url(url))
    # Prefer rental detail links before general sale inventory when scanning is capped.
    found = {u for u in found if not urlsplit(u).path.lower().startswith(("/s/", "/propiedades/venta", "/propiedades/alquiler"))}
    return sorted(found, key=lambda u: (0 if "alquiler" in urlsplit(u).path.lower() else 1, u))[:limit]


def parse_property(html, url, agency):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    for node in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        node.decompose()
    main = soup.select_one("main, article, .property-detail, .single-property, .property-content") or soup.body or soup
    text = " ".join(main.stripped_strings)
    text = re.sub(r"\s+", " ", text)[:12000]
    lead = (title + " " + text[:1600]).strip()
    # Generic navigation sometimes says 'alquiler' even on a SALE listing.
    # Reject obvious land/commercial inventories even if a recommended property is residential.
    if re.search(r"\b(?:lotes?|terrenos?|local(?:\s+comercial)?|galp[oó]n|dep[oó]sito|cochera\s+en|oficina)\b", title + " " + text[:280], re.I) and not re.search(r"\b(?:casa|departamento|\bph\b|d[uú]plex|tr[ií]plex)\b", title, re.I):
        return None, "not residential"
    if not title or not RENT.search(lead):
        return None, "not rental"
    if SALE_ONLY.search(title + " " + text[:200]) and not RENT.search(title):
        return None, "sale"
    if re.search(r"\b(?:USD|U\$S|U\$D)\s*[\d.,]+", title + " " + text[:300], re.I) and not re.search(r"\b(?:ARS|alquiler\s+mensual)\b", title + " " + text[:300], re.I):
        return None, "sale price in USD"
    # A rental listing must not explicitly be marked as rented, reserved or removed.
    if SOLD.search(title + " " + text[:600]):
        return None, "rented/reserved"
    if SALE_ONLY.search(title) and not RENT.search(title):
        return None, "sale"
    neighborhood = next((x for x in NEIGHBORHOODS if re.search(re.escape(x), lead, re.I)), None)
    if not neighborhood:
        return None, "outside defined CABA neighborhoods"
    rooms = [int(m.group(1)) for m in ROOMS.finditer(lead) if 1 <= int(m.group(1)) <= 12]
    beds = [int(m.group(1)) for m in BEDS.finditer(lead) if 1 <= int(m.group(1)) <= 12]
    nrooms = max(rooms, default=0)
    nbeds = max(beds, default=0)
    # Structured headline figures before the photo gallery are more reliable
    # than numbers in recommended listings later on the page.
    primary = lead[:650]
    room_label = re.search(r"\bAmbientes?\s*:?\s*(\d{1,2})\b", primary, re.I)
    bed_label = re.search(r"\bDormitorios?\s*:?\s*(\d{1,2})\b", primary, re.I)
    if room_label and 0 < int(room_label.group(1)) <= 12:
        nrooms = int(room_label.group(1))
    if bed_label and 0 < int(bed_label.group(1)) <= 12:
        nbeds = int(bed_label.group(1))
    # Do not let recommendations or other listings turn a documented
    # 3-ambiente / 2-dormitorio house into a false positive.
    explicit_rooms = re.search(r"\bAmbientes?\s*:?\s*(\d{1,2})\b", text[:850], re.I)
    explicit_beds = re.search(r"\bDormitorios?\s*:?\s*(\d{1,2})\b", text[:850], re.I)
    if explicit_rooms and explicit_beds:
        documented_rooms, documented_beds = int(explicit_rooms.group(1)), int(explicit_beds.group(1))
        if 1 <= documented_rooms <= 12 and 1 <= documented_beds <= 12:
            nrooms, nbeds = documented_rooms, documented_beds
    if nrooms < 4 and nbeds < 3:
        return None, "not 3 dormitorios / 4 ambientes"
    areas = [float(m.group(1).replace(",", ".")) for m in AREA.finditer(lead)]
    area = areas[0] if areas else None
    if area is not None and area < 60:
        return None, "under 60m2"
    price_match = PRICES.search(lead)
    if not price_match:
        return None, "price not verified"
    price = int(re.sub(r"\D", "", price_match.group(1).split(",")[0].split(".")[0] if re.match(r"^\d{5,9}$", price_match.group(1)) else price_match.group(1)))
    # Price with separators is treated as thousands; do not invent if ambiguous.
    if price < 100000 or price > 100000000:
        return None, "price outside expected range"
    address_match = STREET.search(lead)
    address = (address_match.group(0) if address_match else neighborhood + ", CABA")
    images = []
    for meta in soup.select('meta[property="og:image"][content], meta[name="twitter:image"][content]'):
        candidate = urljoin(url, meta.get("content", ""))
        if candidate.startswith("https://") and candidate not in images:
            images.append(candidate)
    category = "PH" if re.search(r"\bph\b|propiedad horizontal", title, re.I) else ("Casa" if re.search("casa|chalet|duplex|dúplex|triplex", title, re.I) else "Departamento")
    stable_id = "agency-" + hashlib.sha256(url.encode()).hexdigest()[:20]
    return {
        "id": stable_id, "mode": "aluguel", "bairro": neighborhood, "address": address,
        "tipo": category, "price": price, "cur": "ARS", "beds": nbeds,
        "area": area, "patio": bool(re.search("patio|pátio|terraza|jardín|jardin", lead, re.I)),
        "garage": bool(re.search("cochera|garage|garaje", lead, re.I)),
        "photo": images[0] if images else None, "photos": images,
        "agency": agency, "url": url, "detail": (title + " — " + lead[:1400]),
        "tag": "Novo no Radar", "verified": "Fonte própria; disponibilidade a confirmar",
        "listing_status": "pending",
    }, "eligible"


def save(session, row, endpoint, key):
    headers = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json", "Prefer": "return=minimal"}
    # Duplicate prevention by exact canonical source URL, including records with older IDs.
    check = session.get(endpoint, params={"select": "id", "url": "eq." + row["url"], "limit": "1"}, headers=headers, timeout=15)
    check.raise_for_status()
    if check.json():
        return "existing"
    alternate = row["url"] + "/" if not row["url"].endswith("/") else row["url"].rstrip("/")
    check_alt = session.get(endpoint, params={"select": "id", "url": "eq." + alternate, "limit": "1"}, headers=headers, timeout=15)
    check_alt.raise_for_status()
    if check_alt.json():
        return "existing"
    resp = session.post(endpoint, json=row, headers=headers, timeout=15)
    resp.raise_for_status()
    return "inserted"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write eligible new records to Supabase")
    ap.add_argument("--max-per-source", type=int, default=40)
    ap.add_argument("--source-limit", type=int, default=0, help="test only N configured agencies")
    ap.add_argument("--source-offset", type=int, default=0, help="skip initial agencies in the config")
    ap.add_argument("--emit-json", action="store_true", help="print eligible candidate records during read-only validation")
    args = ap.parse_args()
    session = requests.Session()
    db_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if args.apply and (not db_url or not key):
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required", file=sys.stderr)
        return 2
    endpoint = db_url + "/rest/v1/radar_caba_listings"
    stats = {"sources": 0, "candidates": 0, "eligible": 0, "inserted": 0, "existing": 0, "errors": 0, "reasons": {}}
    sources = list(SOURCES.items())[max(0, args.source_offset):]
    if args.source_limit > 0:
        sources = sources[:args.source_limit]
    for agency, base in sources:
        urls = candidates(session, base, max(1, min(args.max_per_source, 80)))
        stats["sources"] += 1
        stats["candidates"] += len(urls)
        print(json.dumps({"agency": agency, "candidates": len(urls)}, ensure_ascii=False))
        for url in urls:
            html = fetch(session, url)
            if not html:
                stats["errors"] += 1
                continue
            row, reason = parse_property(html, url, agency)
            if not row:
                stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
                if urls.index(url) < 2:
                    print(json.dumps({"sample_url": url, "reason": reason}, ensure_ascii=False))
            if row:
                stats["eligible"] += 1
                if args.apply:
                    try:
                        action = save(session, row, endpoint, key)
                        stats[action] += 1
                    except requests.RequestException as exc:
                        stats["errors"] += 1
                        print(json.dumps({"url": url, "error": str(exc)[:160]}))
                        continue
                else:
                    action = "dry-run"
                print(json.dumps({"candidate": row, "result": action} if args.emit_json else {"url": url, "rooms": row["beds"], "price": row["price"], "result": action}, ensure_ascii=False))
            time.sleep(0.2)
        time.sleep(0.3)
    print(json.dumps({"summary": stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
