import unittest
from bs4 import BeautifulSoup
from zonaprop_collector import canonical, cards, parsed_card, extract_price, category_urls

def fake_card(url, price, stats, address, description, image, agent=""):
    return f"""
    <div class="postingCard-module__card">
      <img alt="Property photo" src="{image}">
      <div data-qa="POSTING_CARD_PRICE">{price}</div>
      <div data-qa="POSTING_CARD_MAIN_FEATURES">{stats}</div>
      <div data-qa="POSTING_CARD_LOCATION">{address}</div>
      <h2 class="postingCard-module__posting-description" data-qa="POSTING_CARD_DESCRIPTION">
        <a href="{url}">{description}</a>
      </h2>
      <a href="/inmobiliarias/{agent.lower().replace(' ','-')}">{agent}</a>
    </div>
    """


class ZonapropTests(unittest.TestCase):
    def test_category_urls_cover_seven_neighborhoods_and_three_types(self):
        self.assertEqual(len(list(category_urls())), 21)
        self.assertIn(("Mataderos","ph","https://www.zonaprop.com.ar/ph-alquiler-mataderos.html"),list(category_urls()))

    def test_canonical_id_strips_tracking_query(self):
        url,id_=canonical("/propiedades/clasificado/alclcain-casa-mataderos-60595880.html?n_src=Listado&n_pos=1")
        self.assertEqual(id_,"zp-60595880")
        self.assertEqual(url,"https://www.zonaprop.com.ar/propiedades/clasificado/alclcain-casa-mataderos-60595880.html")
        self.assertNotIn("n_src",url)

    def test_extract_does_not_read_neighbor_photos(self):
        a=fake_card(
          "/propiedades/clasificado/alclphin-casa-4-amb-60595880.html?n_src=Listado",
          "$ 1.400.000","80 m² tot. 4 amb. 3 dorm.","Ercilla al 7400",
          "PH tipo casa en alquiler con patio y cochera en Mataderos",
          "https://imgar.zonapropcdn.com/avisos/1/00/60/59/58/80/640x480/test1.jpg",
          "Prueba Propiedades")
        b=fake_card(
          "/propiedades/clasificado/alclcain-casa-4-amb-60595881.html",
          "$ 1.200.000","90 m² tot. 4 amb. 3 dorm.","Basualdo 2000",
          "Casa de 4 ambientes en Mataderos",
          "https://imgar.zonapropcdn.com/avisos/1/00/60/59/58/81/640x480/test2.jpg")
        result=cards(BeautifulSoup("<html><body>"+a+b+"</body></html>","html.parser"))
        self.assertEqual(len(result),2)
        url,card=result["zp-60595880"]
        row=parsed_card(url,"zp-60595880",card,"Mataderos","ph")
        self.assertEqual(row["price"],1400000)
        self.assertEqual(row["agency"],"Prueba Propiedades")
        self.assertEqual(row["address"],"Ercilla al 7400, Mataderos, CABA")
        self.assertIn("/60/59/58/80/",row["photo"])
        self.assertNotIn("/60/59/58/81/",str(row["photos"]))

    def test_currency_and_no_sale_category(self):
        self.assertEqual(extract_price("USD 1.100 por mes"),(1100,"USD"))
        self.assertEqual(extract_price("$ 1.250.000"),(1250000,"ARS"))
        self.assertEqual(extract_price("$ 350.000"),(350000,"ARS"))
        self.assertIsNone(canonical("https://zonaprop.com.ar/casas-venta-mataderos.html")[0])

    def test_skip_small_listings(self):
        markup=fake_card("/propiedades/clasificado/alcldein-mono-60596666.html",
              "$ 700.000","32 m² tot. 1 amb. 1 dorm.","Homero al 300",
              "Monoambiente en alquiler",
              "https://imgar.zonapropcdn.com/avisos/1/00/60/59/66/66/640x480/a.jpg")
        obj=cards(BeautifulSoup(markup,"html.parser"))
        self.assertEqual(len(obj),1)
        url,card=obj["zp-60596666"]
        self.assertIsNone(parsed_card(url,"zp-60596666",card,"Villa Luro","departamentos"))


if __name__=="__main__":
    unittest.main()
