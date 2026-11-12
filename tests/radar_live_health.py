"""Read-only health check against the production Radar JSON API."""
import json
import sys
import urllib.request
from collections import Counter

URL="https://radar-casas-caba.vercel.app/api/listings"
request=urllib.request.Request(URL,headers={"Accept":"application/json","User-Agent":"RadarCABA-Healthcheck/1.0"})
with urllib.request.urlopen(request,timeout=25) as response:
    if response.status != 200:
        raise AssertionError("Production API returned non-200 status")
    data=json.load(response)

rows=data.get("listings",[])
agencies=data.get("agencies",[])
assert isinstance(rows,list) and len(rows)>=200, f"Expected substantial fresh inventory, found {len(rows)}"
assert isinstance(agencies,list) and len(agencies)>=30, "Agency catalog missing"
counts=Counter(str(row.get("agency") or "") for row in rows)
for agency in ("Roman Propiedades","Pablo Saullo e Hijos","Todoroff Propiedades","Florencio Gonzalez Inmuebles"):
    assert counts[agency]>0, f"Production API missing {agency}"
maccaroni=[x for x in rows if x.get("agency")=="Maccaroni"]
with_gallery=sum(len(x.get("photos") or [])>=3 for x in maccaroni)
assert with_gallery>=15, f"Maccaroni galleries missing: {with_gallery} with >=3 photos"
print("RADAR_PRODUCTION_API_OK "+json.dumps({
    "total":len(rows),"agencies":len(agencies),"rentals":sum(x.get("mode")=="aluguel" for x in rows),
    "sales":sum(x.get("mode")=="venda" for x in rows),
    "requested_agencies":{k:counts[k] for k in ("Roman Propiedades","Pablo Saullo e Hijos","Todoroff Propiedades","Florencio Gonzalez Inmuebles")},
    "maccaroni_galleries_3plus":with_gallery
},ensure_ascii=False))
