#!/usr/bin/env python3
"""Independent read-only audit of *all* Radar CABA agency sources.

Unlike the listing collector, this audit does not require an eligible 3-bedroom
rental to consider a source functional. A source is verified when a concrete
property detail page is reachable and exposes property-specific content.
"""
import argparse
import concurrent.futures
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from collector import candidates, browser_candidates, parse_property, PROPERTY_PATH

SNAPSHOT = Path(__file__).with_name("audit_sources.json")
LIVE_AGENCIES = "https://qfuflpvxcgvivsihlkwb.supabase.co/functions/v1/radar-casas-dados"
PROPERTY_TERMS = re.compile(r"\b(?:departamento|depto|casa|ph|d[uú]plex|ambientes?|dormitorios?|alquiler|venta|superficie|habitaciones?|m2|m²|propiedad)\b", re.I)
PRICELIKE = re.compile(r"(?:U\$S|USD|ARS|\$\s*[\d.,]+|\b\d+\s*(?:m²|m2)\b)", re.I)
GENERIC = re.compile(r"^(?:inicio|home|buscador de propiedades|propiedades|b[uú]squeda de propiedades|en construcción|404|página no encontrada)$", re.I)
DEFAULT_AUDIT_GROUPS = 8


def sources_from_snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))["agencies"]


def load_sources():
    snapshot = sources_from_snapshot()
    try:
        response = requests.get(LIVE_AGENCIES, timeout=12, headers={"accept": "application/json"})
        response.raise_for_status()
        data = response.json()
        live = data.get("agencies")
        if isinstance(live, list) and len(live) >= len(snapshot) and all(isinstance(x, dict) and x.get("name") for x in live):
            print(json.dumps({"audit_meta": "live_agencies_loaded", "count": len(live)}, ensure_ascii=False), flush=True)
            return live
        print(json.dumps({"audit_warning": "live inventory unavailable or incomplete; using 73-source snapshot"}), flush=True)
    except (requests.RequestException, ValueError, TypeError) as exc:
        print(json.dumps({"audit_warning": "live inventory failed; using 73-source snapshot", "error": str(exc)[:150]}), flush=True)
    return snapshot


def probe(session, url):
    try:
        response = session.get(url, timeout=10, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (compatible; RadarCABA-Audit/1.0)"})
        return {"http": response.status_code, "url": response.url, "body": response.text if response.status_code == 200 else ""}
    except requests.RequestException as exc:
        return {"http": None, "url": url, "body": "", "error": str(exc)[:110]}


def inspect_detail(session, url, agency):
    response = probe(session, url)
    if response["http"] != 200:
        return {"url": url, "http": response["http"], "usable": False, "error": response.get("error", "")}
    html = response["body"]
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("h1")
    name = title.get_text(" ", strip=True)[:130] if title else ""
    for node in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        node.decompose()
    main = soup.select_one("main, article, .property-detail, .single-property, .property-content") or soup.body or soup
    text = main.get_text(" ", strip=True)[:6000]
    joined = name + " " + text
    slug = urlsplit(url).path.rsplit("/", 1)[-1].replace("-", " ")
    property_named = bool(PROPERTY_TERMS.search(name + " " + slug))
    metrics = bool(PRICELIKE.search(joined[:2400]))
    detail_markers = bool(PROPERTY_TERMS.search(text[:1600]))
    generic_title = bool(GENERIC.match(name.strip()))
    readable = len(text) >= 160
    # A category page with navigation and search controls is not property detail.
    usable = bool(readable and property_named and detail_markers and metrics and not generic_title)
    try:
        row, reason = parse_property(html, url, agency)
        target = bool(row)
    except Exception:
        target = False
    return {
        "url": url, "http": 200, "usable": usable,
        "title": name, "text_chars": len(text),
        "has_property_terms": detail_markers,
        "has_price_or_area": metrics,
        "eligible_target": target
    }


def audit_one(agency, browser=False, max_details=3):
    name = agency["name"]
    url = agency.get("url")
    result = {
        "id": agency.get("id"), "name": name, "url": url,
        "source_kind": "portal_profile" if url and any(p in urlsplit(url).hostname.lower() for p in ("argenprop.com", "zonaprop.com.ar")) else "agency_site",
        "site_http": None, "site_ok": False, "links_found": 0,
        "details_checked": 0, "details_http_200": 0,
        "details_usable": 0, "eligible_in_sample": 0,
        "status": None, "samples": [], "errors": []
    }
    if not url:
        result["source_kind"] = "no_catalogue"
        result["status"] = "no_site"
        return result
    session = requests.Session()
    try:
        home = probe(session, url)
        result["site_http"] = home["http"]
        result["site_ok"] = home["http"] == 200 and bool(home["body"])
        result["resolved_url"] = home["url"]
        if home.get("error"):
            result["errors"].append("home: " + home["error"])
        try:
            links = candidates(session, url, limit=32)
        except Exception as exc:
            links = []
            result["errors"].append("candidate_collection: " + str(exc)[:120])
        if browser and (not links or name in ("Maccaroni", "Inmobiliaria Falco", "Heiber Osornio", "Varcasia Propiedades", "Acosta")):
            try:
                more = browser_candidates(url, name, limit=32)
                links = list(dict.fromkeys(list(links) + more))
                result["used_browser"] = True
            except Exception as exc:
                result["errors"].append("browser: " + str(exc)[:120])
        result["links_found"] = len(links)
        for candidate in links[:max_details]:
            detail = inspect_detail(session, candidate, name)
            result["details_checked"] += 1
            result["details_http_200"] += int(detail["http"] == 200)
            result["details_usable"] += int(detail["usable"])
            result["eligible_in_sample"] += int(detail.get("eligible_target", False))
            result["samples"].append(detail)
        if result["details_usable"]:
            result["status"] = "details_verified"
        elif result["links_found"] and result["details_http_200"]:
            result["status"] = "details_visible_unparsed"
        elif result["links_found"]:
            result["status"] = "links_only"
        elif result["site_ok"]:
            result["status"] = "site_reachable_no_links"
        else:
            result["status"] = "site_unreachable"
    finally:
        session.close()
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", type=int, default=0)
    ap.add_argument("--groups", type=int, default=8)
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-details", type=int, default=3)
    ap.add_argument("--only", default="", help="Select one agency by exact name")
    args = ap.parse_args()
    sources = load_sources()
    if args.only:
        selected = [x for x in sources if x["name"].casefold() == args.only.casefold()]
    else:
        selected = [x for i, x in enumerate(sources) if i % args.groups == args.group]
    print(json.dumps({"audit_meta": "group_start", "group": args.group, "source_count": len(selected)}, ensure_ascii=False), flush=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        futures = {pool.submit(audit_one, x, args.browser, args.max_details): x for x in selected}
        for future in concurrent.futures.as_completed(futures):
            agency = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"id": agency.get("id"), "name": agency["name"], "url": agency.get("url"), "status": "audit_error", "error": str(exc)[:250]}
            results.append(result)
            print("SOURCE_AUDIT " + json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    print("AUDIT_SUMMARY " + json.dumps({
        "group": args.group, "count": len(results),
        "statuses": {s: sum(x.get("status") == s for x in results) for s in sorted(set(x.get("status") for x in results))},
        "links": sum(x.get("links_found", 0) for x in results),
        "usable": sum(x.get("details_usable", 0) for x in results)
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
