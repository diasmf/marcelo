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
    "Jorge Reale": "https://www.argenprop.com/inmobiliarias/jorge-reale-group/inmuebles",
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
    "Varcasia Propiedades": "https://www.varcasiapropiedades.com.ar/",
    "Crivez Silvana": "https://www.crivezsilvana-propiedades.com.ar/",
    "Fedele Inmobiliaria": "https://www.argenprop.com/inmobiliarias/fedele-inmobiliaria/ph",
    "Todoroff Propiedades": "https://www.argenprop.com/inmobiliarias/todoroff-propiedades/inmuebles/mataderos",
    "Florencio Gonzalez Inmuebles": "https://florenciogonzalez.com.ar/",
    # Catalogued agencies now included in the collector.
    "Naccarato Propiedades": "https://www.naccaratopropiedades.com.ar/propiedades/",
    "Maqueda Propiedades": "https://www.maqueda.com.ar/propiedades",
    "Roman Propiedades": "https://inmobiliariaroman.com.ar/",
    "Paladino Negocios Inmobiliarios": "https://www.paladinoprop.com.ar/estado/en-alquiler/",
    "Jose Pintimalli Propiedades": "https://www.josepintimalli.com.ar/Buscar",
    "Werba Inmuebles": "https://www.werba.com.ar/",
    "Ing. E. A. Villamil Propiedades": "https://www.ingenierovillamil.com.ar/",
    # Nine newly added independent real-estate agencies in western CABA.
    "Gentile Inmuebles": "https://gentileinmuebles.com/",
    "Amalfitani Inmuebles": "https://www.amalfitani.com.ar/",
    "Yacopino Inmobiliarias": "https://www.yacopino.com.ar/",
    "Dicons Propiedades": "https://www.diconspropiedades.com/",
    "Liotto Propiedades": "https://liottopropiedades.com.ar/",
    "FJ Lujan Propiedades": "https://www.fjlujan.com.ar/",
    "Gamez Propiedades": "https://www.gamezpropiedades.com.ar/",
    "Norde Propiedades": "https://www.nordepropiedades.com.ar/",
    "Tizado Villa Luro": "https://www.tizado.com/",
    # Additional agencies discovered through local map/business search.
    "Massaro Propiedades": "https://massaropropiedades.com.ar/",
    "Gustavo Vega Propiedades": "https://gustavovegapropiedades.com.ar/",
    "Martorell Propiedades": "https://martorellprop.com.ar/",
    "Inmobiliaria Monferini SRL": "https://monferinisrl.com.ar/",
    "SegurBA Propiedades": "https://www.segurba.com.ar/",
    "Golden Haus Luro": "https://www.goldenhaus.com.ar/inmobiliaria/",
    # Confirmed in the source audit, previously missing from the active collector.
    "Carro Propiedades": "https://carropropiedades.com.ar/properties",
    "Enrique Cannone Propiedades": "https://www.cannonepropiedades.com.ar/",
    "Jakim Propiedades": "https://www.jakimpropiedades.com/",
    "Pablo Saullo e Hijos": "https://pablosaulloehijos.com.ar/propiedades/",
    "RE/MAX Fly Liniers": "https://www.remax-fly.com.ar/",
}
PROPERTY_PATH = re.compile(r"/(?:propiedad(?:es)?/[^/?#]+|(?:casa|ph|departamento|duplex|triplex)[^/?#]*/[^/?#]+|(?:ph|casa|departamento)-alquiler-[^/?#]+/[^/?#]+|inmueble/[^/?#]+|ficha-[^/?#]+|(?:casa|ph|departamento)-en-(?:alquiler|venta)[^/?#]*ficha-[^/?#]+|p/\d{5,}-[^/?#]+|properties/(?:departamento|casa|ph)/[^/?#]+/[^/?#]+|properties-2/\d+-[^/?#]+|propiedades-en-[^/?#]+/[^/?#]+/(?:casa|ph|departamento|duplex|triplex)-en-(?:alquiler|venta)-[^/?#]+|listings/[^/?#]+|propiedad-\d+-[^/?#]+|ficha/[^/?#]+|propiedad\.asp|vitalefeol-\d+|(?:casa|ph|departamento)-en-(?:alquiler|venta)-en-[^/?#]+)", re.I)
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
    query = ""
    # Preserve the listing identifier on Gamez's propiedad.asp URLs.
    if "gamezpropiedades.com.ar" in p.netloc.lower() and p.path.lower().endswith("/propiedad.asp"):
        match = re.search(r"(?:^|&)idpropiedad=(\d+)", p.query, re.I)
        if match:
            query = "idpropiedad=" + match.group(1)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", query, ""))


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
    # First-party rental catalogue pages: a homepage alone misses many rentals.
    category_paths = []
    if "inmofalco.com.ar" in host:
        category_paths = ["/estado/en-alquiler/"]
    elif "elaltilloinmuebles.com.ar" in host:
        category_paths = ["/alquiler/"]
    elif "giacolettopropiedades.com" in host:
        category_paths = ["/Alquiler", "/Propiedades"]
    elif "estudioheiberosornio.com" in host:
        category_paths = ["/Alquiler", "/Casas", "/PHs", "/Departamentos"]
    elif "maccaroni.com.ar" in host:
        category_paths = ["/propiedades?ope=A", "/propiedades?ope=A&tipo=C", "/propiedades?ope=A&tipo=P", "/propiedades?ope=A&tipo=D"]
    elif "naccaratopropiedades.com.ar" in host:
        category_paths = ["/propiedades/"]
    elif "maqueda.com.ar" in host:
        category_paths = ["/propiedades", "/alquileres"]
    elif "inmobiliariaroman.com.ar" in host:
        category_paths = ["/propiedades", "/alquiler"]
    elif "paladinoprop.com.ar" in host:
        category_paths = ["/estado/en-alquiler/", "/propiedades/"]
    elif "josepintimalli.com.ar" in host:
        category_paths = ["/Buscar", "/Alquiler"]
    elif "werba.com.ar" in host:
        category_paths = ["/Alquiler", "/Propiedades"]
    elif "ingenierovillamil.com.ar" in host:
        category_paths = ["/Alquiler", "/Propiedades"]
    elif "gentileinmuebles.com" in host:
        category_paths = ["/alquileres", "/ventas"]
    elif "amalfitani.com.ar" in host:
        category_paths = ["/alquiler", "/propiedades", "/buscador-de-propiedades"]
    elif "yacopino.com.ar" in host:
        category_paths = ["/busqueda-de-propiedades-en-alquiler"]
    elif "diconspropiedades.com" in host:
        category_paths = ["/Alquiler", "/Propiedades"]
    elif "liottopropiedades.com.ar" in host:
        category_paths = ["/property-type/alquiler/", "/property-type/alquiler/casa/", "/property-type/alquiler/departamento/"]
    elif "fjlujan.com.ar" in host:
        category_paths = ["/Alquiler"]
    elif "gamezpropiedades.com.ar" in host:
        category_paths = ["/alquiler.asp", "/Alquiler"]
    elif "nordepropiedades.com.ar" in host:
        category_paths = ["/Alquiler", "/home_properties/"]
    elif "tizado.com" in host:
        category_paths = ["/propiedades", "/alquiler"]
    elif "massaropropiedades.com.ar" in host:
        category_paths = ["/propiedades"]
    elif "gustavovegapropiedades.com.ar" in host:
        category_paths = ["/propiedades"]
    elif "martorellprop.com.ar" in host:
        category_paths = ["/inmuebles/alquiler/", "/inmuebles/venta/"]
    elif "monferinisrl.com.ar" in host:
        category_paths = ["/propiedades/"]
    elif "segurba.com.ar" in host:
        category_paths = ["/alquiler.php", "/venta.php"]
    elif "goldenhaus.com.ar" in host:
        category_paths = ["/inmobiliaria/"]
    elif "carropropiedades.com.ar" in host:
        category_paths = ["/properties", "/properties-2"]
    elif "cannonepropiedades.com.ar" in host:
        category_paths = ["/propiedades?ope=A", "/propiedades?ope=V", "/propiedades"]
    elif "jakimpropiedades.com" in host:
        category_paths = ["/propiedades?ope=A", "/propiedades?ope=V", "/propiedades"]
    elif "pablosaulloehijos.com.ar" in host:
        category_paths = ["/propiedades/", "/alquileres"]
    elif "remax-fly.com.ar" in host:
        category_paths = ["/propiedades-en-caba/departamentos-en-capital-federal", "/propiedades-en-caba/casas-en-capital-federal", "/propiedades-en-caba/ph-en-capital-federal"]
    elif "varcasiapropiedades.com.ar" in host:
        category_paths = ["/Alquiler", "/Propiedades"]
    elif any(domain in host for domain in (
        "borrajopropiedades.com.ar", "varelavillalba.com.ar",
        "clompropiedades.com.ar", "parajonpropiedades.com.ar",
        "pallarols-santander.com", "leonelacullaripropiedades.com",
        "magnaccapatelli.com", "vitalefeola.com.ar",
        "bienesraicesmg.com.ar", "jorgereale.com",
        "crivezsilvana-propiedades.com.ar", "xn--abraa-rta.com.ar")):
        category_paths = ["/Alquiler", "/Propiedades"]
    elif "acostainmobiliaria.com.ar" in host:
        category_paths = ["/propiedades?ope=A", "/propiedades?ope=A&tipo=C",
                          "/propiedades?ope=A&tipo=D", "/propiedades?ope=A&tipo=P"]
    elif "xn--abraa-rta.com.ar" in host:
        category_paths = ["/propiedades"]
    elif "magnaccapatelli.com" in host:
        category_paths = ["/alquileres.php", "/alquiler.php"]
    elif "bienesraicesmg.com.ar" in host:
        category_paths = ["/properties", "/propiedades"]
    elif "vitalefeola.com.ar" in host:
        category_paths = ["/propiedades", "/index"]
    for page in [base] + [urljoin(base, path) for path in category_paths]:
        html = fetch(session, page)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            url = urljoin(page, a["href"])
            if same_host(urlsplit(url).hostname, host) and (
                PROPERTY_PATH.search(urlsplit(url).path)
                or ("martorellprop.com.ar" in host and page.rstrip("/").endswith(("/inmuebles/alquiler", "/inmuebles/venta"))
                    and re.search(r"/[^/?#]*(?:casa|ambientes|depto|ph-)[^/?#]*/?$", urlsplit(url).path, re.I))
            ):
                found.add(clean_url(url))
    # Prefer rental detail links before general sale inventory when scanning is capped.
    found = {u for u in found if not urlsplit(u).path.lower().startswith(("/s/", "/propiedades/venta", "/propiedades/alquiler"))}
    return sorted(found, key=lambda u: (0 if "alquiler" in urlsplit(u).path.lower() else 1, u))[:limit]


def browser_candidates(base, agency, limit=80):
    """Load Javascript-rendered first-party listings; no API, no write access."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Install playwright and chromium to use --browser")
    host = urlsplit(base).hostname
    pages = [base]
    if agency == "Maccaroni":
        pages = [urljoin(base, p) for p in (
            "/propiedades?ope=A", "/propiedades?ope=A&tipo=C",
            "/propiedades?ope=A&tipo=P", "/propiedades?ope=A&tipo=D")]
    elif agency == "Inmobiliaria Falco":
        pages = [urljoin(base, "/estado/en-alquiler/"),urljoin(base,"/propiedades/")]
    elif agency == "Heiber Osornio":
        pages = [urljoin(base,p) for p in ("/Alquiler","/Casas","/PHs","/Departamentos")]
    elif agency == "Varcasia Propiedades":
        pages = [urljoin(base,p) for p in ("/Alquiler","/Propiedades")]
    elif agency == "Acosta":
        pages = [urljoin(base,p) for p in (
            "/propiedades?ope=A", "/propiedades?ope=A&tipo=C",
            "/propiedades?ope=A&tipo=D", "/propiedades?ope=A&tipo=P")]
    elif agency in ("MG Bienes Raíces", "Vitale Feola Propiedades"):
        pages = [base, urljoin(base, "/propiedades"), urljoin(base, "/properties")]
    elif agency=="Braña Inmobiliaria":
        pages=[base,urljoin(base,"/propiedades")]
    elif agency=="Magnacca Patelli Propiedades":
        pages=[base,urljoin(base,"/alquileres.php"),urljoin(base,"/alquiler.php")]
    elif agency in ("Enrique Cannone Propiedades", "Jakim Propiedades"):
        pages=[base]+[urljoin(base,p) for p in ("/propiedades?ope=A", "/propiedades?ope=V", "/propiedades")]
    elif agency=="Carro Propiedades":
        pages=[base,urljoin(base,"/properties-2")]
    links=set()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        context=browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36")
        page=context.new_page()
        try:
            for catalog in pages:
                try:
                    response=page.goto(catalog,wait_until="domcontentloaded",timeout=16000)
                    if not response or response.status>=400:
                        continue
                    page.wait_for_timeout(2600 if agency=="Maccaroni" else 900)
                    for href in page.locator("a[href]").evaluate_all("(nodes)=>nodes.map(n=>n.href)"):
                        if same_host(urlsplit(href).hostname,host) and PROPERTY_PATH.search(urlsplit(href).path):
                            links.add(clean_url(href))
                except Exception as exc:
                    print(json.dumps({"catalog":catalog,"error":str(exc)[:120]}))
        finally:
            browser.close()
    return sorted(links,key=lambda u:(0 if "alquiler" in u.lower() else 1,u))[:limit]


def browser_property_html(urls):
    """Read listing text rendered inside a site's same-window and iframe documents."""
    from playwright.sync_api import sync_playwright
    results={}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        context=browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36")
        page=context.new_page()
        try:
            for url in urls:
                try:
                    response=page.goto(url,wait_until="domcontentloaded",timeout=15000)
                    if not response or response.status>=400:
                        continue
                    page.wait_for_timeout(1100)
                    contents=[page.content()]
                    for frame in page.frames:
                        if frame==page.main_frame or frame.url=="about:blank":
                            continue
                        try:
                            contents.append(frame.content())
                        except Exception:
                            pass
                    # Property content can be nested in a Xintel/Amaira iframe.
                    # Keep the main document too for canonical address and photos.
                    content=max(contents,key=lambda html: len(BeautifulSoup(html,"html.parser").get_text(" ",strip=True)))
                    results[url]=content
                except Exception as exc:
                    print(json.dumps({"property_url":url,"browser_property_error":str(exc)[:110]}))
        finally:
            browser.close()
    return results


def parse_property(html, url, agency):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    detail_url = bool(re.search(r"/p/\d{5,}-|ficha-mco\d+|/propiedad/\d+_",urlsplit(url).path,re.I))
    if detail_url and (not title or re.search(r"^(?:buscador de propiedades|b[uú]squeda de propiedades|propiedades|inmuebles|inicio|home)\b",title,re.I)):
        # Many agencies use generic H1 on every page despite unique rental detail URLs.
        # Derive only the property type and operation from the explicit URL, not site navigation.
        raw = urlsplit(url).path.rstrip("/").rsplit("/",1)[-1]
        if "/p/" in urlsplit(url).path:
            raw = re.sub(r"^\d+-", "",raw)
        raw = re.sub(r"-ficha-[^-]+$", "",raw,flags=re.I)
        title = raw.replace("-", " ").replace("_"," ").strip().title()
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
    if not title or re.search(r"^(?:buscador de propiedades|b[uú]squeda de propiedades|propiedades|inmuebles|inicio|home)\b", title, re.I):
        return None, "generic search page"
    if not RENT.search(lead):
        return None, "not rental"
    # Do not offer commercial-only properties to people looking for a home.
    if re.search(r"\buso\s+comercial\b|\boficinas?\s+y\s+dep[oó]sito\b", title + " " + text[:800], re.I):
        return None, "commercial-only use"
    if SALE_ONLY.search(title + " " + text[:200]) and not RENT.search(title):
        return None, "sale"
    if re.search(r"\b(?:USD|U\$S|U\$D)\s*[\d.,]+", title + " " + text[:300], re.I) and not re.search(r"\b(?:ARS|alquiler\s+mensual)\b", title + " " + text[:300], re.I):
        return None, "sale price in USD"
    # A rental listing must not explicitly be marked as rented, reserved or removed.
    if SOLD.search(title + " " + text[:600]):
        return None, "rented/reserved"
    if SALE_ONLY.search(title) and not RENT.search(title):
        return None, "sale"
    # Address/title comes before agency footer and related-property navigation.
    neighborhood = next((x for x in NEIGHBORHOODS if re.search(re.escape(x), title, re.I)), None)
    if not neighborhood:
        neighborhood = next((x for x in NEIGHBORHOODS if re.search(re.escape(x), text[:650], re.I)), None)
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
    for img in soup.select("main img[src], main img[data-src], article img[src], .gallery img[src], .property-gallery img[src]"):
        raw = img.get("data-src") or img.get("src") or ""
        candidate = urljoin(url, raw)
        path = urlsplit(candidate).path.lower()
        if (candidate.startswith("https://") and re.search(r"\.(?:jpe?g|png|webp)$", path)
                and not re.search(r"logo|avatar|icon|banner|placeholder|tracking|profile", path)
                and candidate not in images):
            images.append(candidate)
        if len(images) >= 30:
            break
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
    ap.add_argument("--source-name", default="", help="test only the specified agency")
    ap.add_argument("--browser", action="store_true", help="discover listings using browser-rendered agency catalogues")
    args = ap.parse_args()
    session = requests.Session()
    db_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if args.apply and (not db_url or not key):
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required", file=sys.stderr)
        return 2
    endpoint = db_url + "/rest/v1/radar_caba_listings"
    stats = {"sources": 0, "candidates": 0, "eligible": 0, "inserted": 0, "existing": 0, "errors": 0, "reasons": {}, "source_status": {}}
    sources = list(SOURCES.items())
    if args.source_name:
        sources = [(name,base) for name,base in sources if name.lower()==args.source_name.lower()]
    else:
        sources = sources[max(0,args.source_offset):]
    if args.source_limit > 0:
        sources = sources[:args.source_limit]
    for agency, base in sources:
        urls = candidates(session, base, max(1, min(args.max_per_source, 80)))
        if args.browser and agency in ("Maccaroni","Inmobiliaria Falco","Heiber Osornio","Varcasia Propiedades","Acosta","MG Bienes Raíces","Vitale Feola Propiedades","Braña Inmobiliaria","Magnacca Patelli Propiedades","Enrique Cannone Propiedades","Jakim Propiedades","Carro Propiedades"):
            try:
                browser_urls = browser_candidates(base, agency, max(1,min(args.max_per_source,80)))
                urls = sorted(set(urls)|set(browser_urls),key=lambda u:(0 if "alquiler" in u.lower() else 1,u))[:max(1,min(args.max_per_source,80))]
            except Exception as exc:
                print(json.dumps({"agency":agency,"browser_error":str(exc)[:180]},ensure_ascii=False))
        rendered={}
        if args.browser and agency in ("Maccaroni","Acosta","MG Bienes Raíces","Enrique Cannone Propiedades","Jakim Propiedades") and urls:
            try:
                rendered=browser_property_html(urls)
            except Exception as exc:
                print(json.dumps({"agency":agency,"browser_page_error":str(exc)[:150]}))
        stats["sources"] += 1
        stats["candidates"] += len(urls)
        if urls:
            status = "candidate_links_found"
        else:
            status = "reachable_no_property_links" if fetch(session,base) else "source_unreachable"
        stats["source_status"][agency] = status
        print(json.dumps({"agency": agency, "candidates": len(urls), "source_status": status}, ensure_ascii=False))
        for url in urls:
            html = rendered.get(url) or fetch(session,url)
            if not html:
                stats["errors"] += 1
                if urls.index(url)<2:
                    print(json.dumps({"sample_url":url,"reason":"detail fetch failed"},ensure_ascii=False))
                continue
            row, reason = parse_property(html, url, agency)
            if not row and reason=="generic search page" and rendered.get(url):
                print(json.dumps({"property_url":url,"rendered_title":BeautifulSoup(html,"html.parser").title.get_text(" ",strip=True)[:100] if BeautifulSoup(html,"html.parser").title else "","rendered_chars":len(html)}))
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
