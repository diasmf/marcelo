"""Regression smoke test for Radar agency filter and diagnostic mode (no upload controls)."""
import json
import threading
import http.server
import socketserver
from playwright.sync_api import sync_playwright

def record(id,agency,beds,area,status="pending",mode="aluguel"):
    return {
        "id":id,"mode":mode,"bairro":"Liniers","address":id,"tipo":"Casa","price":1200000,
        "cur":"ARS","beds":beds,"area":area,"patio":False,"garage":False,
        "photo":None,"photos":[],"agency":agency,"url":"https://example.org/propiedad/"+id,
        "detail":"Casa en alquiler, Liniers, 2 ambientes" if beds==1 else "Casa 4 ambientes en alquiler",
        "listing_status":status,"discovered_at":"2026-11-11"
    }

sample={
 "listings":[record("casa-a","Maccaroni",3,110),
             record("casa-b","Maccaroni",1,45),
             record("casa-inativa","Maccaroni",3,120,"inactive"),
             record("casa-c","Bosich",3,115)],
 "agencies":[{"name":"Maccaroni","bairro":"Liniers","url":"https://maccaroni.com.ar/"},
             {"name":"Bosich","bairro":"Liniers","url":"https://bosichbienesraices.com.ar/"},
             {"name":"Zero Testes","bairro":"Liniers","url":"https://example.org/"}]
}

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

with socketserver.TCPServer(("127.0.0.1",0),Quiet) as server:
    host=f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1200,"height":860})
        errors=[]
        page.on("pageerror",lambda err:errors.append(str(err)))
        page.route("**/api/listings",lambda route:route.fulfill(status=200,content_type="application/json",body=json.dumps(sample)))
        page.goto(host+"/radar-casas/index.html",wait_until="domcontentloaded")
        page.wait_for_function("document.querySelectorAll('#agencyFilter option').length >= 4",timeout=10000)
        assert page.locator("#cards article.card").count()==2, "default shows two qualifying active rentals"
        page.select_option("#agencyFilter",label="Maccaroni")
        assert page.locator("#cards article.card").count()==1, "agency filter should narrow default rentals"
        page.locator("#diagnosticMode").check()
        assert page.locator("#cards article.card").count()==3, "diagnostic should show both invalid and inactive properties"
        assert "INATIVO" in page.locator("#cards").inner_text(), "inactive must be marked"
        page.locator("#diagnosticMode").uncheck()
        assert page.locator("#cards article.card").count()==1
        page.locator('[data-tab="agencies"]').click()
        page.locator('[data-testagency="Zero Testes"]').click()
        assert page.locator("#cards article.card").count()==0, "zero-listing source must show no results"
        assert page.locator("#diagnosticMode").is_checked()
        assert not errors, errors
        print("RADAR_FILTER_SMOKE_OK: agency, diagnostic, inactive warnings, zero listings")
        browser.close()
    server.shutdown()
