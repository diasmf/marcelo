#!/usr/bin/env python3
"""Smoke test production Radar photo carousel, using public listings only."""
import json
import re
import subprocess
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE = "https://radar-casas-caba.vercel.app"
html = Path("radar-casas/index.html").read_text(encoding="utf-8")
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.I|re.S)
if not scripts:
    raise RuntimeError("No inline JavaScript found")
Path("/tmp/radar-frontend-check.js").write_text("\n;\n".join(scripts),encoding="utf-8")
subprocess.run(["node", "--check", "/tmp/radar-frontend-check.js"], check=True)
print("UI_JS_SYNTAX_OK",flush=True)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
    page=browser.new_page(viewport={"width":1050,"height":880})
    errors=[]
    page.on("pageerror",lambda e: errors.append(str(e)[:200]))
    resp=page.goto(BASE,wait_until="domcontentloaded",timeout=30000)
    print("UI_HOME_HTTP",resp.status if resp else "none",flush=True)
    page.wait_for_timeout(5000)
    page.evaluate("""()=>{
      const c=document.querySelector("#diagnosticMode");
      if(c){c.checked=true;c.dispatchEvent(new Event('input',{bubbles:true}));}
    }""")
    page.wait_for_timeout(1400)
    total=page.locator("article.card").count()
    zcards=page.locator('article.card:has(a[href*="zonaprop.com.ar"])').count()
    photos=page.locator("article.card img.slide[data-zoom]").count()
    buttons=page.locator("article.card .photo button.zoom, article.card .photo button.photo-more, article.card .photo a.gallery").count()
    print("UI_COUNTS",json.dumps({"cards":total,"zonaprop_cards":zcards,"photo_elements":photos,"extra_photo_buttons":buttons,"page_errors":errors[:3]}),flush=True)
    if total==0 or photos==0 or buttons:
        raise AssertionError("No cards/photos or unused overlay buttons still visible")
    # A multi-photo card must actually change the displayed image and count.
    multi=page.locator("article.card:has(.photo-next)").first
    assert multi.count(), "At least one property should expose multiple photos"
    first_src=multi.locator("img.slide:visible").first.get_attribute("src")
    first_counter=multi.locator(".photo-count").inner_text()
    multi.locator("button.photo-next").click()
    second_src=multi.locator("img.slide:visible").first.get_attribute("src")
    second_counter=multi.locator(".photo-count").inner_text()
    assert first_src != second_src, "Next arrow did not change the photo"
    assert first_counter != second_counter, "Next arrow did not update the counter"
    print("UI_NEXT_PHOTO_PASS",json.dumps({"before":first_counter,"after":second_counter}),flush=True)
    img=page.locator("article.card img.slide[data-zoom]:visible").first
    img.scroll_into_view_if_needed()
    img.click(timeout=6000)
    page.wait_for_timeout(250)
    lightbox=page.locator("#photoLightbox")
    assert lightbox.evaluate("(e)=>e.classList.contains('open')"),"Click did not open photo modal"
    page.locator("#closeLightbox").click()
    assert not lightbox.evaluate("(e)=>e.classList.contains('open')"),"Modal did not close"
    card=page.locator("article.card:has(a[href*='zonaprop.com.ar'])").first
    if zcards:
        source_image=card.locator("img.slide:visible")
        if source_image.count():
            photo_url=source_image.first.get_attribute("src")
            response=requests.get(photo_url,headers={"User-Agent":"Mozilla/5.0"},timeout=15,stream=True)
            print("ZONAPROP_CDN",json.dumps({"http":response.status_code,"mime":response.headers.get("Content-Type",""),"bytes":response.headers.get("Content-Length","unknown")}),flush=True)
            response.close()
    print("UI_GALLERY_SMOKE_PASS",flush=True)
    browser.close()
