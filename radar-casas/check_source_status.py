#!/usr/bin/env python3
"""Daily conservative availability checks for existing Radar listings.

Does not remove records. It records confirmed HTTP 200 / 404 / 410 responses
so the authorized Supabase ingestion endpoint can hide a listing only after
two independent days of genuine 404/410 responses. Transient outages never
count as removals. User ratings and notes are not touched.
"""
import argparse
import concurrent.futures
import json
import threading
from pathlib import Path
from urllib.parse import urlsplit

import requests

API = "https://qfuflpvxcgvivsihlkwb.supabase.co/functions/v1/radar-casas-dados"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarCABA-StatusAudit/1.0)", "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.7"}
home_cache = {}
home_lock = threading.Lock()


def same_page(left, right):
    a, b = urlsplit(left), urlsplit(right)
    return (a.hostname or "").lower().removeprefix("www.") == (b.hostname or "").lower().removeprefix("www.") and a.path.rstrip("/") == b.path.rstrip("/")


def root_works(url):
    host = urlsplit(url).hostname
    if not host:
        return False
    with home_lock:
        if host in home_cache:
            return home_cache[host]
    try:
        resp = requests.get("https://" + host + "/", headers=HEADERS, timeout=(5, 11), stream=True, allow_redirects=True)
        status = resp.status_code
        resp.close()
        good = 200 <= status < 400
    except requests.RequestException:
        good = False
    with home_lock:
        home_cache[host] = good
    return good


def inspect(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=(5, 15), stream=True, allow_redirects=True)
        status = r.status_code
        final = r.url
        r.close()
        if status == 200 and same_page(url, final):
            return {"url": url, "status": 200}
        if status in (404, 410) and same_page(url, final) and root_works(url):
            return {"url": url, "status": status}
        return None
    except requests.RequestException:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=5)
    parser.add_argument("--max-samples", type=int, default=0, help="limit records for a safe smoke test")
    parser.add_argument("--export-path", required=True)
    args = parser.parse_args()
    if args.shards < 1 or not 0 <= args.shard < args.shards:
        parser.error("invalid shard")
    response = requests.get(API, timeout=30, headers={"accept": "application/json"})
    response.raise_for_status()
    data = response.json()
    if not isinstance(data.get("listings"), list):
        raise RuntimeError("Radar source did not return a listings array")
    candidates = sorted({
        l["url"] for l in data["listings"]
        if isinstance(l, dict)
        and l.get("listing_status") != "inactive"
        and isinstance(l.get("url"), str)
        and l["url"].startswith("https://")
    })
    chosen = [url for i, url in enumerate(candidates) if i % args.shards == args.shard]
    if args.max_samples > 0:
        chosen = chosen[:args.max_samples]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for r in executor.map(inspect, chosen):
            if r:
                results.append(r)
    target = Path(args.export_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"kind": "availability", "checks": results}, ensure_ascii=False), encoding="utf-8")
    counts = {str(s): sum(1 for r in results if r["status"] == s) for s in (200, 404, 410)}
    print(json.dumps({"availability_shard": args.shard, "checked": len(chosen), "reliable_responses": len(results), "http_status": counts, "skipped_transient_or_uncertain": len(chosen) - len(results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
