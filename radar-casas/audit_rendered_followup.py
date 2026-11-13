#!/usr/bin/env python3
"""Read-only second pass for sources that failed the HTML-only audit.

Uses a real browser, including same-page frames, and checks property-specific
detail content without applying the user's rent/beds/area/price criteria.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import sync_playwright
from collector import PROPERTY_PATH, same_host, clean_url
from audit_all_sources import PROPERTY_TERMS, PRICELIKE

REPORT = Path(__file__).with_name("audit_latest.json")
NAV = re.compile(r"alquiler|venta|inmueble|propiedad|buscador|listado|buscar|cat[aá]logo|oferta", re.I)
DETAIL_SLUG = re.compile(r"(?:alquiler|venta|departamento|depto|casa|chalet|ambientes|[-/]ph[-/]|ficha|propiedad/\d+|/p/\d+)", re.I)


def eligible_link(url, site):
    try:
        src = urlsplit(url)
        if src.scheme != "https" or not same_host(src.hostname, urlsplit(site).hostname):
            return False
        path = src.path
        if (re.search(r"/(?:page|pagina|category|tag|estado|propiedades)/(?:\d+)?/?$", path, re.I)
            or re.search(r"/(?:propiedades|alquiler|venta|buscar|inmuebles)/?$", path, re.I)):
            return False
        return bool(PROPERTY_PATH.search(path) or (DETAIL_SLUG.search(path) and len(path.strip("/")) > 18))
    except (TypeError, ValueError):
        return False


def capture(page, url):
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=16000)
        page.wait_for_timeout(1700)
        status = response.status if response else None
        frames = []
        for frame in page.frames:
            try:
                text = frame.locator("body").inner_text(timeout=3000)
                h1 = frame.locator("h1").all_inner_texts()[:2]
                frames.append({"frame": frame.url[:190], "chars": len(text), "text": text[:11000], "headings": [str(x).strip()[:130] for x in h1]})
            except Exception:
                continue
        valid_texts = [f for f in frames if len(f["text"]) > 110]
        best = max(valid_texts, key=lambda f: int(bool(PRICELIKE.search(f["text"]))) * 15000 + len(f["text"]), default=None)
        title = (best["headings"][0] if best and best["headings"] else "")
        content = best["text"] if best else ""
        is_property_url = eligible_link(url, url)
        content_has_property = bool(PROPERTY_TERMS.search(content[:6000]))
        content_has_numbers = bool(PRICELIKE.search(content[:6000]))
        confirmed = bool(status and status < 400 and is_property_url and len(content) > 170 and content_has_property and content_has_numbers)
        anchors = []
        try:
            anchors = page.locator("a[href]").evaluate_all("(els)=>els.map(e=>({url:e.href,text:(e.innerText||'').trim().slice(0,90)}))")[:1000]
        except Exception:
            pass
        return {"url": url, "status": status, "resolved": page.url, "title": title, "chars": len(content),
                "has_property": content_has_property, "has_price_or_area": content_has_numbers,
                "frames": len(frames), "confirmed": confirmed, "links": anchors}
    except Exception as exc:
        return {"url": url, "status": None, "confirmed": False, "error": str(exc)[:160], "links": []}


def followup_one(context, before):
    url = before.get("url")
    if not url:
        return {"name": before["name"], "status": "no_site", "before": before["status"]}
    page = context.new_page()
    try:
        original = before["status"]
        samples = [s["url"] for s in before.get("samples", []) if s.get("url")]
        found = set(s for s in samples if eligible_link(s, url))
        first = capture(page, url)
        candidate_nav = [x["url"] for x in first.get("links", [])
                         if same_host(urlsplit(x["url"]).hostname, urlsplit(url).hostname)
                         and (NAV.search(x["text"]+" "+x["url"]) and x["url"].rstrip("/") != url.rstrip("/"))]
        for item in first.get("links", []):
            if eligible_link(item["url"], url):
                found.add(clean_url(item["url"]))
        # Search rendered catalogues only when direct property links are not found.
        if not found:
            for nav in list(dict.fromkeys(candidate_nav))[:3]:
                listing = capture(page, nav)
                for item in listing.get("links", []):
                    if eligible_link(item["url"], url):
                        found.add(clean_url(item["url"]))
        details = []
        for listing_url in list(found)[:2]:
            detail = capture(page, listing_url)
            details.append({k: v for k, v in detail.items() if k != "links"})
        verified = sum(bool(x.get("confirmed")) for x in details)
        return {
            "name": before["name"], "id": before.get("id"), "url": url,
            "before": original,
            "status": "details_verified" if verified else original,
            "site_browser_status": first["status"],
            "browser_links": len(found), "verified_details": verified,
            "checked": len(details), "details": details
        }
    finally:
        page.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", type=int, default=0)
    ap.add_argument("--groups", type=int, default=6)
    args = ap.parse_args()
    first = json.loads(REPORT.read_text(encoding="utf-8"))["sources"]
    unresolved = [x for x in first if x["status"] not in ("details_verified", "no_site")]
    selected = [x for i, x in enumerate(unresolved) if i % args.groups == args.group]
    print(json.dumps({"followup_group": args.group, "selected": len(selected)}, ensure_ascii=False), flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36")
        try:
            for before in selected:
                try:
                    result = followup_one(context, before)
                except Exception as exc:
                    result = {"name": before["name"], "before": before["status"], "status": before["status"], "error": str(exc)[:160]}
                print("RENDER_AUDIT " + json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
