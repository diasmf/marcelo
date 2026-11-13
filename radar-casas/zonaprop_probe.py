#!/usr/bin/env python3
"""Diagnostics only: inspect publicly reachable Zonaprop rental category HTML."""
import json
import re
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
CATEGORIES=[
"https://www.zonaprop.com.ar/casas-alquiler-mataderos.html",
"https://www.zonaprop.com.ar/ph-alquiler-mataderos.html",
"https://www.zonaprop.com.ar/ph-alquiler-villa-luro.html",
"https://www.zonaprop.com.ar/propiedades/clasificado/alclphpa-ph-tipo-casa-en-planta-baja-barrio-naon-60595880.html",
]
HEADERS={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml","Accept-Language":"es-AR,es;q=0.9"}
for url in CATEGORIES:
    try:
        r=requests.get(url,headers=HEADERS,timeout=18)
        h=BeautifulSoup(r.text,"html.parser")
        links=[(a.get("href"),a.get_text(" ",strip=True)[:60]) for a in h.select("a[href]") if re.search(r"/propiedades/clasificado/[^?#]*\d{7,9}\.html",a.get("href",""),re.I)]
        attrs=[]
        for a in h.select("a[href]"):
            if re.search(r"/propiedades/clasificado/[^?#]*\d{7,9}\.html",a.get("href",""),re.I):
                for ancestor in list(a.parents)[:6]:
                    if ancestor.has_attr("data-id") or ancestor.has_attr("data-qa") or ancestor.has_attr("class") and re.search(r"post|listing|card|advert",str(ancestor.get("class")),re.I):
                        attrs.append({"tag":ancestor.name,"class":ancestor.get("class"),"qa":ancestor.get("data-qa"),"data_id":ancestor.get("data-id"),"summary":ancestor.get_text(" ",strip=True)[:480]})
                        break
                if len(attrs)>=2:break
        print(json.dumps({"url":url,"status":r.status_code,"bytes":len(r.content),"final_url":r.url,"title":h.title.get_text(" ",strip=True) if h.title else None,"links":len(links),"examples":links[:4],"card_samples":attrs,"jsonld":len(h.select('script[type="application/ld+json"]')),"next_data":bool(h.select_one("script#__NEXT_DATA__")),"challenge":bool(re.search(r"captcha|just a moment|access denied|enable javascript",h.title.get_text(" ",strip=True) if h.title else "",re.I))},ensure_ascii=False),flush=True)
    except requests.RequestException as e: print(json.dumps({"url":url,"error":str(e)[:180]},ensure_ascii=False),flush=True)
    time.sleep(.65)
