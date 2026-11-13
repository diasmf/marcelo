#!/usr/bin/env python3
"""Diagnostics only: inspect publicly reachable Zonaprop rental category HTML."""
import json
import re
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from zonaprop_collector import photos_by_id
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
        if r.status_code==200 and url.endswith("casas-alquiler-mataderos.html"):
            from zonaprop_collector import cards
            sample=cards(h)
            target=h.select_one('a[href*="53716927.html"]') or h.select_one('a[href*="/propiedades/clasificado/"]')
            if target:
                parents=[]
                for anc in list(target.parents)[:12]:
                    if not getattr(anc,"name",None):continue
                    imgs=anc.select('img')
                    parents.append({"tag":anc.name,"cls":anc.get("class"),"links":len(anc.select('a[href*="/propiedades/clasificado/"]')),"images":len(imgs),"img_attrs":[dict(x.attrs) for x in imgs[:2]],"text_len":len(anc.get_text(" ",strip=True))})
                print("ANCESTORS_DEBUG",json.dumps(parents,ensure_ascii=False),flush=True)
            ld=[]
            for tag in h.select('script[type="application/ld+json"]'):
                raw=tag.string or tag.get_text()
                if raw and ('53716927' in raw or 'Pola 1411' in raw):
                    ld.append(raw[:2500])
            print("JSONLD_DEBUG",json.dumps(ld[:3],ensure_ascii=False),flush=True)
            print("BODY_PHOTO_COUNTS",json.dumps({"imgs":len(h.select('img')),"og":len(h.select('meta[property="og:image"]')),"img_samples":[dict(a.attrs) for a in h.select('img')[:8]]},ensure_ascii=False),flush=True)
            if sample:
                key,(su,card)=next(iter(sample.items()))
                imgs=card.select("img")
                print("CARD_DEBUG",json.dumps({"id":key,"url":su,"card_html":str(card)[:6500],"img_attrs":[dict(x.attrs) for x in imgs[:8]],"pictures":[str(x)[:500] for x in card.select("picture,source")[:6]],"backgrounds":[str(x)[:400] for x in card.select("[style]")[:4]],"card_classes":card.get("class"),"card_text":card.get_text(" ",strip=True)[:900]},ensure_ascii=False),flush=True)
        if url.endswith("casas-alquiler-mataderos.html"):
            first=h.select_one('a[href*="/propiedades/clasificado/"]')
            if first:
                parents=list(first.parents)[:9]
                print("FIRST_ANCHOR",json.dumps({"href":first.get("href"),"text":first.get_text(" ",strip=True)[:180],"parent_layers":[{"tag":p.name,"class":p.get("class"),"data_qa":p.get("data-qa"),"data_id":p.get("data-id"),"text_len":len(p.get_text(" ",strip=True))} for p in parents if getattr(p,"name",None)],"parent_3_html":str(parents[3])[:6000],"parent_5_html":str(parents[5])[:11000]},ensure_ascii=False),flush=True)
            print("QA_ELEMENTS",json.dumps([{"tag":x.name,"qa":x.get("data-qa"),"tag_class":x.get("class"),"text":x.get_text(" ",strip=True)[:65]} for x in h.select("[data-qa]")[:55]],ensure_ascii=False),flush=True)
        if r.status_code==200:
            groups=photos_by_id(h)
            print("PHOTO_DIAGNOSTIC "+json.dumps({"url":url,"groups":len(groups),"with_three":sum(1 for v in groups.values() if isinstance(v,list) and len(v)>=3),"samples":list(groups.items())[:5],"jsonld":len(h.select('script[type="application/ld+json"]'))},ensure_ascii=False),flush=True)
            if "casas-alquiler-mataderos" in url and links:
                detail_url=urljoin(url,links[0][0])
                try:
                    d=requests.get(detail_url,headers=HEADERS,timeout=14)
                    ds=BeautifulSoup(d.text,"html.parser")
                    images=photos_by_id(ds)
                    print("DETAIL_DIAGNOSTIC "+json.dumps({"url":detail_url,"status":d.status_code,"groups":len(images),"first":list(images.items())[:2]},ensure_ascii=False),flush=True)
                except requests.RequestException as exc:
                    print("DETAIL_DIAGNOSTIC "+json.dumps({"url":detail_url,"error":str(exc)[:160]},ensure_ascii=False),flush=True)
        print(json.dumps({"url":url,"status":r.status_code,"bytes":len(r.content),"final_url":r.url,"title":h.title.get_text(" ",strip=True) if h.title else None,"links":len(links),"examples":links[:4],"card_samples":attrs,"jsonld":len(h.select('script[type="application/ld+json"]')),"next_data":bool(h.select_one("script#__NEXT_DATA__")),"challenge":bool(re.search(r"captcha|just a moment|access denied|enable javascript",h.title.get_text(" ",strip=True) if h.title else "",re.I))},ensure_ascii=False),flush=True)
    except requests.RequestException as e: print(json.dumps({"url":url,"error":str(e)[:180]},ensure_ascii=False),flush=True)
    time.sleep(.65)
