"""Regression smoke test for Radar agency filter and diagnostic mode (no upload controls)."""
import json
import struct
import zlib
import threading
import http.server
import socketserver
from playwright.sync_api import sync_playwright

def record(id,agency,beds,area,status="pending",mode="aluguel"):
    return {
        "id":id,"mode":mode,"bairro":"Liniers","address":id,"tipo":"Casa","price":1200000,
        "cur":"ARS","beds":beds,"area":area,"patio":False,"garage":False,
        "photo":None if id=="sem-foto" else "https://radar-photo.test/"+id+"-01.png",
        "photos":[] if id=="sem-foto" else
          ["https://radar-photo.test/"+id+"-01.png",
           "https://radar-photo.test/"+id+("-broken" if id=="casa-c" else "-02")+".png",
           "https://radar-photo.test/"+id+"-03.png"],
        "agency":agency,"url":"https://example.org/propiedad/"+id,
        "detail":"Casa en alquiler, Liniers, 2 ambientes" if beds==1 else "Casa 4 ambientes en alquiler",
        "listing_status":status,"discovered_at":"2026-11-11"
    }

sample={
 "listings":[record("casa-a","Maccaroni",3,110),
             record("casa-b","Maccaroni",1,45),
             record("casa-inativa","Maccaroni",3,120,"inactive"),
             record("casa-c","Bosich",3,115),
             record("sem-foto","Maccaroni",3,108)],
 "agencies":[{"name":"Maccaroni","bairro":"Liniers","url":"https://maccaroni.com.ar/","audit_status":"links_found","audit_links_found":24,"audit_checked_at":"2026-11-11T19:11:07Z"},
             {"name":"Bosich","bairro":"Liniers","url":"https://bosichbienesraices.com.ar/","audit_status":"no_links","audit_links_found":0},
             {"name":"Zero Testes","bairro":"Liniers","url":"https://example.org/","audit_status":"unreachable","audit_links_found":0},
             {"name":"Florencio González","bairro":"Liniers","url":"https://florenciogonzalez.com.ar/","audit_status":"links_found","audit_links_found":165},
             {"name":"Florencio Gonzalez Inmuebles","bairro":"Liniers","url":"https://florenciogonzalez.com.ar/","audit_status":"links_found","audit_links_found":165}]
}

# Small valid 400x300 image served locally; no external image host is needed.
def png_image():
    def chunk(tag,payload):
        return struct.pack(">I",len(payload))+tag+payload+struct.pack(">I",zlib.crc32(tag+payload)&0xffffffff)
    pixels=(b"\x00"+b"\x55\x8b\x70"*400)*300
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",400,300,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b"")

PHOTO=png_image()

def mock_photo(route):
    if "-broken.png" in route.request.url:
        route.fulfill(status=404,body="Missing")
    else:
        route.fulfill(status=200,content_type="image/png",body=PHOTO)

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
        page.route("https://radar-photo.test/**",mock_photo)
        page.goto(host+"/radar-casas/index.html",wait_until="domcontentloaded")
        page.wait_for_function("document.querySelectorAll('#agencyFilter option').length >= 4",timeout=10000)
        assert page.locator("#cards article.card").count()==2, "default shows two qualifying active rentals"
        page.wait_for_function("document.querySelector('#subtitle').textContent.includes('imóveis')")
        assert page.locator(".photo-count").count()>=2, "carousels should show multiple photos"
        first=page.locator('article.card:has([data-zoom="casa-a"])')
        assert first.locator("[data-count]").inner_text()=="1 / 3"
        first.locator('[data-advance="1"]').click()
        assert first.locator("[data-count]").inner_text()=="2 / 3"
        first.locator('[data-zoom="casa-a"]').click()
        assert page.locator("#photoLightbox").get_attribute("class")=="open"
        assert "2 de 3" in page.locator("#lbCaption").inner_text()
        page.click("#closeLightbox")
        assert "open" not in page.locator("#photoLightbox").get_attribute("class")
        # Image that fails on the second slide is removed without breaking navigation.
        broken=page.locator('article.card:has([data-zoom="casa-c"])')
        broken.locator('[data-advance="1"]').click()
        page.wait_for_function("document.querySelector('[data-zoom=\\\"casa-c\\\"]') && document.querySelector('article.card:has([data-zoom=\\\"casa-c\\\"]) [data-count]').textContent.endsWith('/ 2')",timeout=10000)
        assert page.locator('#cards').inner_text().count('sem-foto')==0, "no-photo listing hidden from normal cards"
        # Optional controls live in a collapsed <details> panel.
        page.locator("#moreFilters summary").click()
        page.select_option("#agencyFilter",label="Maccaroni")
        assert page.locator("#cards article.card").count()==1, "agency filter should narrow default rentals"
        assert page.locator("#minBeds").input_value()=="3"
        assert page.locator("#minRooms").input_value()=="4"
        assert page.locator("#minArea").input_value()=="60"
        page.select_option("#minBeds","1")
        page.select_option("#minRooms","")
        page.fill("#minArea","")
        assert page.locator("#cards article.card").count()==2, "custom bedrooms must include small rental"
        page.fill("#minArea","60")
        assert page.locator("#cards article.card").count()==1, "area threshold must filter small rental"
        page.click("#mainPreset")
        assert page.locator("#minBeds").input_value()=="3"
        assert page.locator("#minRooms").input_value()=="4"
        assert page.locator("#minArea").input_value()=="60"
        assert page.locator("#cards article.card").count()==1
        assert page.locator("#mainPreset").get_attribute("aria-pressed")=="true"
        page.click("#mainPreset")
        assert page.locator("#mainPreset").get_attribute("aria-pressed")=="false"
        assert page.locator("#minBeds").input_value()==""
        assert page.locator("#minRooms").input_value()==""
        assert page.locator("#minArea").input_value()==""
        assert page.locator("#cards article.card").count()==2, "toggle off must remove room and area restrictions without showing inactive"
        page.click("#mainPreset")
        assert page.locator("#mainPreset").get_attribute("aria-pressed")=="true"
        assert page.locator("#cards article.card").count()==1, "toggle on restores the standard criteria"
        page.click("#showAllPreset")
        assert page.locator("#cards article.card").count()==4
        assert page.locator("#diagnosticMode").is_checked()
        page.click("#mainPreset")
        assert not page.locator("#diagnosticMode").is_checked()
        assert page.locator("#cards article.card").count()==1
        page.locator("#diagnosticMode").check()
        assert page.locator("#cards article.card").count()==3, "diagnostic should show both invalid and inactive properties"
        assert "INATIVO" in page.locator("#cards").inner_text(), "inactive must be marked"
        page.locator("#diagnosticMode").uncheck()
        assert page.locator("#cards article.card").count()==1
        page.locator('[data-tab="agencies"]').click()
        agency_text=page.locator("#agencyCards").inner_text()
        assert page.locator("#agencyCards .agent").count()==4, "duplicate Florencio records must make one agency card"
        assert agency_text.count("Florencio González")==1, "canonical agency only once"
        assert "Anúncios no Radar" in agency_text
        assert "Coleta verificada" in agency_text
        assert "24 links encontrados" in agency_text
        assert "Falha de acesso no teste" in agency_text
        assert "Zero fichas cadastradas não significa zero anúncios no mercado" in agency_text
        page.locator('[data-testagency="Zero Testes"]').click()
        assert page.locator("#cards article.card").count()==0, "zero-listing source must show no results"
        assert page.locator("#diagnosticMode").is_checked()
        assert not errors, errors
        print("RADAR_FILTER_SMOKE_OK: agency, preset, individual bedroom and area filters, diagnostic, inactive warnings, zero listings")
        mobile=browser.new_page(viewport={"width":390,"height":844},device_scale_factor=2,is_mobile=True,has_touch=True)
        mobile.route("**/api/listings",lambda route:route.fulfill(status=200,content_type="application/json",body=json.dumps(sample)))
        mobile.route("https://radar-photo.test/**",mock_photo)
        mobile.goto(host+"/radar-casas/index.html",wait_until="domcontentloaded")
        mobile.wait_for_function("document.querySelectorAll('#cards article.card').length===2",timeout=10000)
        assert mobile.locator('article.card:has([data-zoom="casa-a"]) [data-count]').inner_text()=="1 / 3"
        mobile.locator('article.card:has([data-zoom="casa-a"]) [data-advance="1"]').click()
        assert mobile.locator('article.card:has([data-zoom="casa-a"]) [data-count]').inner_text()=="2 / 3"
        mobile.close()
        browser.close()
    server.shutdown()
