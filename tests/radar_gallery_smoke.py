"""Browser smoke test for Maccaroni local-gallery feature, including persistence."""
import base64, json, threading, http.server, socketserver
from playwright.sync_api import sync_playwright

sample = {
 "listings":[{"id":"radar-gallery-test","mode":"aluguel","bairro":"Mataderos",
 "address":"Mataderos, CABA","tipo":"Casa","price":1800000,"cur":"ARS",
 "beds":3,"area":110,"patio":True,"garage":False,
 "photo":"https://images.example.com/first.png",
 "photos":["https://images.example.com/first.png"],
 "agency":"Maccaroni",
 "url":"https://www.maccaroni.com.ar/casa-en-alquiler-en-mataderos-ficha-mco3934",
 "detail":"Casa en alquiler, Mataderos", "tag":"Novo no Radar",
 "listing_status":"pending","discovered_at":"2026-11-10"}],
 "agencies":[]
}
png=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==")

class Silent(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass

with socketserver.TCPServer(("127.0.0.1",0),Silent) as server:
 host=f"http://127.0.0.1:{server.server_address[1]}"
 threading.Thread(target=server.serve_forever,daemon=True).start()
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  page=browser.new_page()
  page.route("**/api/listings",lambda r:r.fulfill(status=200,content_type="application/json",body=json.dumps(sample)))
  page.route("https://images.example.com/first.png",lambda r:r.fulfill(status=200,content_type="image/png",body=png))
  errors=[]
  page.on("pageerror",lambda err:errors.append(str(err)))
  page.goto(host+"/radar-casas/index.html",wait_until="domcontentloaded")
  page.locator('[data-addlocal="radar-gallery-test"]').wait_for(timeout=10000)
  page.locator('#localGalleryPicker').set_input_files([
   {"name":"interior1.png","mimeType":"image/png","buffer":png},
   {"name":"interior2.png","mimeType":"image/png","buffer":png},
  ])
  page.locator('[data-count="radar-gallery-test"]').wait_for(timeout=10000)
  assert page.locator('[data-count="radar-gallery-test"]').inner_text()=="1 / 3"
  page.locator('[data-advance="1"][data-id="radar-gallery-test"]').click()
  assert page.locator('[data-count="radar-gallery-test"]').inner_text()=="2 / 3"
  page.reload(wait_until="domcontentloaded")
  page.locator('[data-count="radar-gallery-test"]').wait_for(timeout=10000)
  assert page.locator('[data-count="radar-gallery-test"]').inner_text()=="1 / 3"
  assert not errors, errors
  browser.close()
  print("GALLERY_SMOKE_OK: upload, arrow navigation, indexedDB persistence")
 server.shutdown()
