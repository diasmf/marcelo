#!/usr/bin/env python3
"""Upload collector batches with short-lived GitHub Actions OIDC, no service key."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode

import requests

AUDIENCE = "radar-caba-ingest"
ENDPOINT = "https://qfuflpvxcgvivsihlkwb.supabase.co/functions/v1/radar-github-ingest"


def github_oidc_token(session):
    url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL")
    bearer = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not bearer:
        raise RuntimeError("GitHub OIDC is not enabled for this job (id-token: write permission)")
    join = "&" if "?" in url else "?"
    response = session.get(
        url + join + urlencode({"audience": AUDIENCE}),
        headers={"Authorization": "Bearer " + bearer},
        timeout=20,
    )
    response.raise_for_status()
    token = response.json().get("value")
    if not isinstance(token, str) or token.count(".") != 2:
        raise RuntimeError("GitHub OIDC provider did not return a usable identity token")
    return token


def send(session, data, token):
    response = session.post(
        ENDPOINT,
        json=data,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        timeout=120,
    )
    try:
        result = response.json()
    except ValueError:
        result = {"error": "invalid response"}
    if not response.ok or not result.get("ok"):
        raise RuntimeError("Ingest rejected batch (HTTP %s): %s" % (response.status_code, json.dumps(result)[:850]))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-path", help="JSON exported by collector.py")
    parser.add_argument("--probe", action="store_true", help="verify OIDC connection without writing")
    args = parser.parse_args()
    if not args.batch_path and not args.probe:
        parser.error("--batch-path or --probe is required")
    with requests.Session() as session:
        token = github_oidc_token(session)
        tested = send(session, {"kind": "probe"}, token)
        print(json.dumps({"identity": "verified", "repository": tested.get("repository"), "run_id": tested.get("run_id")}))
        if args.probe:
            return 0
        batch = json.loads(Path(args.batch_path).read_text(encoding="utf-8"))
        if batch.get("kind") != "upsert" or not isinstance(batch.get("sources"), list) or not isinstance(batch.get("listings"), list):
            raise RuntimeError("Invalid collector export format")
        batch["run_id"] = os.getenv("GITHUB_RUN_ID", "")
        batch["shard"] = os.getenv("RADAR_SOURCE_OFFSET", "")
        result = send(session, batch, token)
        print(json.dumps({"uploaded_sources": len(batch["sources"]), "eligible_rows": len(batch["listings"]), "ingestion": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
