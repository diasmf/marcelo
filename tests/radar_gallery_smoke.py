"""Regression smoke test for Radar agency filter and diagnostic mode (no upload controls)."""
import json
import struct
import zlib
import threading
import http.server
import socketserver
from playwright.sync_api import sync_playwright
from datetime import datetime, timezone

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
# Long listing text should never make the initial card dominate the screen.
LONG_DESCRIPTION = ("Casa 4 ambientes en alquiler, com sala ampla, quartos iluminados, "
                    "cozinha separada e pátio. " * 10) + "FINAL DA DESCRIÇÃO ORIGINAL"
sample["listings"][0]["detail"] = LONG_DESCRIPTION

# Small valid 400x300 image served locally; no external image host is needed.
def png_image():
    def chunk(tag,payload):
        return struct.pack(">I",len(payload))+tag+payload+struct.pack(">I",zlib.crc32(tag+payload)&0xffffffff)
    pixels=(b"\x00"+b"\x55\x8b\x70"*400)*300
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",400,300,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b"")

PHOTO=png_image()

def mock_fx(route):
    route.fulfill(status=200,content_type="application/json",body=json.dumps({
        "casa":"bolsa","nombre":"Dólar MEP","venta":1600.0,"compra":1590.0,
        "fechaActualizacion":datetime.now(timezone.utc).isoformat()
    }))

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
        page.route("https://dolarapi.com/v1/dolares/bolsa",mock_fx)
        page.goto(host+"/radar-casas/index.html",wait_until="domcontentloaded")
        page.wait_for_function("document.querySelectorAll('#agencyFilter option').length >= 4",timeout=10000)
        assert page.locator("#cards article.card").count()==2, "default shows two qualifying active rentals"
        assert page.locator("#rentBudgetEnabled").is_checked()
        assert page.locator("#budgetLabel").inner_text()=="US$ 600–1.200"
        page.wait_for_function("document.querySelector('#rentFxHelp').textContent.includes('1.600')")
        assert "960.000" in page.locator("#rentFxHelp").inner_text()
        assert "1.920.000" in page.locator("#rentFxHelp").inner_text()
        assert page.locator(".hero").bounding_box()["height"]<190, "desktop hero must be compact"
        assert "5 aluguéis cadastrados" in page.locator("#inventorySummary").inner_text()
        assert "3 exibíveis" in page.locator("#inventorySummary").inner_text()
        assert "1 marcados inativos" in page.locator("#inventorySummary").inner_text()
        assert "1 sem fotos" in page.locator("#inventorySummary").inner_text()
        assert page.locator("#showAllPreset").is_visible()
        page.wait_for_function("document.querySelector('#subtitle').textContent.includes('imóveis')")
        assert page.locator(".photo-count").count()>=2, "carousels should show multiple photos"
        first=page.locator('article.card:has([data-zoom="casa-a"])')
        assert first.locator(".note-expand").count()==1
        assert first.locator(".note-expand").get_attribute("open") is None
        assert first.locator("details.detail-expand").count()==1
        assert first.locator("details.detail-expand").get_attribute("open") is None
        assert first.locator(".detail-preview").evaluate(
            "(el) => getComputedStyle(el).getPropertyValue('-webkit-line-clamp')")=="2"
        assert first.locator(".detail-preview").bounding_box()["height"] < 70
        first.locator("details.detail-expand summary").click()
        assert first.locator(".detail-full").is_visible()
        assert "FINAL DA DESCRIÇÃO ORIGINAL" in first.locator(".detail-full").inner_text()
        assert first.locator('a:has-text("Anúncio original")').get_attribute("href")=="https://example.org/propiedad/casa-a"
        first.locator("details.detail-expand summary").click()
        assert first.locator("details.detail-expand").get_attribute("open") is None
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
        assert page.locator("#agencyFilter").input_value()=="", "all-registered must reset the agency filter"
        assert page.locator("#cards article.card").count()==5
        page.select_option("#agencyFilter",label="Maccaroni")
        assert page.locator("#cards article.card").count()==4
        assert page.locator("#diagnosticMode").is_checked()
        page.click("#mainPreset")
        assert not page.locator("#diagnosticMode").is_checked()
        assert page.locator("#cards article.card").count()==1
        page.locator("#diagnosticMode").check()
        assert page.locator("#cards article.card").count()==4, "diagnostic should also show the no-photo record"
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
        mobile.route("https://dolarapi.com/v1/dolares/bolsa",mock_fx)
        mobile.goto(host+"/radar-casas/index.html",wait_until="domcontentloaded")
        mobile.wait_for_function("document.querySelectorAll('#cards article.card').length===2",timeout=10000)
        assert mobile.locator('article.card:has([data-zoom="casa-a"]) [data-count]').inner_text()=="1 / 3"
        assert mobile.locator(".hero").bounding_box()["height"]<250, "mobile hero must remain compact"
        mobile_description=mobile.locator('article.card:has([data-zoom="casa-a"]) details.detail-expand')
        assert mobile_description.count()==1
        assert mobile_description.get_attribute("open") is None
        assert mobile_description.locator(".detail-preview").bounding_box()["height"] < 70
        mobile_description.locator("summary").click()
        assert "FINAL DA DESCRIÇÃO ORIGINAL" in mobile_description.locator(".detail-full").inner_text()
        mobile_description.locator("summary").click()
        mobile.locator('article.card:has([data-zoom="casa-a"]) [data-advance="1"]').click()
        assert mobile.locator('article.card:has([data-zoom="casa-a"]) [data-count]').inner_text()=="2 / 3"
        mobile.close()
        # Test direct USD prices and MEP-converted ARS prices with customizable FX.
        budget_listings=[
            record("usd-800","Maccaroni",3,120),
            record("usd-1300","Maccaroni",3,120),
            record("ars-1500000","Maccaroni",3,120),
            record("ars-2000000","Maccaroni",3,120),
            record("ars-800000","Maccaroni",3,120),
            record("ars-1900000","Maccaroni",3,120),
            record("sale-100000","Maccaroni",3,120,mode="venda"),
        ]
        prices=[("USD",800),("USD",1300),("ARS",1500000),("ARS",2000000),
                ("ARS",800000),("ARS",1900000),("USD",100000)]
        for listing,(cur,price) in zip(budget_listings,prices):
            listing["cur"]=cur
            listing["price"]=price
        # A syndication-only agency may have listings but no catalogue record.
        budget_listings[0]["agency"]="New Broker"
        budget_payload={"listings":budget_listings,"agencies":sample["agencies"]}
        budget_page=browser.new_page(viewport={"width":1200,"height":860})
        budget_page.route("**/api/listings",lambda route:route.fulfill(status=200,content_type="application/json",body=json.dumps(budget_payload)))
        budget_page.route("https://radar-photo.test/**",mock_photo)
        budget_page.route("https://dolarapi.com/v1/dolares/bolsa",mock_fx)
        budget_page.goto(host+"/radar-casas/index.html",wait_until="domcontentloaded")
        budget_page.wait_for_function("document.querySelector('#rentFxHelp').textContent.includes('1.600')")
        assert budget_page.locator("#cards article.card").count()==3, "USD 800 and ARS 1.5m / 1.9m qualify at MEP 1600"
        assert "usd-1300" not in budget_page.locator("#cards").inner_text()
        assert "ars-2000000" not in budget_page.locator("#cards").inner_text()
        budget_page.locator("#rentBudgetEnabled").uncheck()
        assert budget_page.locator("#cards article.card").count()==6, "budget can be disabled without dropping rental records"
        budget_page.locator("#rentBudgetEnabled").check()
        assert budget_page.locator("#cards article.card").count()==3
        budget_page.locator("#moreFilters summary").click()
        budget_page.fill("#fxRate","1400")
        assert budget_page.locator("#cards article.card").count()==2, "ARS 1.9m exceeds USD 1200 at FX 1400"
        budget_page.fill("#rentMaxUsd","900")
        assert budget_page.locator("#cards article.card").count()==1, "custom maximum applies to both currencies"
        budget_page.locator('[data-tab="venda"]').click()
        assert budget_page.locator("#cards article.card").count()==1, "rent budget must not hide property sales"
        assert not budget_page.locator("#rentBudgetBar").is_visible()
        budget_page.locator('[data-tab="agencies"]').click()
        assert budget_page.locator("#otherAgencyGroup").is_visible(), "listing-only advertisers must be visible separately"
        budget_page.locator("#otherAgencyGroup summary").click()
        assert "New Broker" in budget_page.locator("#otherAgencyCards").inner_text()
        budget_page.locator('[data-testagency="New Broker"]').click()
        assert budget_page.locator("#agencyFilter").input_value()=="New Broker"
        assert budget_page.locator("#cards article.card").count()==1, "listing-only agency selection must show its source"
        budget_page.close()
        print("RADAR_BUDGET_SMOKE_OK: MEP, USD/ARS thresholds, manual FX, toggling, sale isolation, compact cards")
        browser.close()
    server.shutdown()
