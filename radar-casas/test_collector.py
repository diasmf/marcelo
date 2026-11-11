import unittest
from collector import parse_property

def page(title, text):
    return '<html><head><meta property="og:image" content="https://images.example.org/property1.jpg"></head><body><main><h1>'+title+'</h1><p>'+text+'</p></main></body></html>'

class PropertyParsingTests(unittest.TestCase):
    def test_eligible_four_ambientes(self):
        html=page("Casa 4 ambientes en alquiler en Monte Castro", "Lascano 5055, Monte Castro. $ 1.800.000. 3 dormitorios. Superficie total 220 m². Patio y terraza.")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/42","Test Agency")
        self.assertEqual(reason,"eligible")
        self.assertEqual(row["price"],1800000)
        self.assertEqual(row["beds"],3)
        self.assertEqual(row["bairro"],"Monte Castro")
        self.assertEqual(row["area"],220)

    def test_four_ambientes_two_bedrooms_is_eligible(self):
        html=page("PH 4 ambientes en alquiler en Liniers", "Liniers, Capital Federal. $ 900.000. 2 dormitorios. Sup. total 100 m².")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/43","Test Agency")
        self.assertEqual(reason,"eligible")
        self.assertEqual(row["beds"],2)

    def test_exclude_alquilado(self):
        html=page("PH 4 ambientes en alquiler en Liniers", "Alquilado. Liniers. $ 900.000. 3 dormitorios. Superficie total 100 m².")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/44","Test Agency")
        self.assertIsNone(row)
        self.assertEqual(reason,"rented/reserved")

    def test_exclude_small(self):
        html=page("Casa 4 ambientes en alquiler Mataderos", "Mataderos. $ 900.000. 3 dormitorios. Superficie total 48 m².")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/45","Test Agency")
        self.assertEqual(reason,"under 60m2")

    def test_exclude_two_rooms(self):
        html=page("Departamento 2 ambientes en alquiler Liniers", "Liniers. $ 700.000. 1 dormitorio. Superficie 100 m².")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/46","Test Agency")
        self.assertEqual(reason,"not 3 dormitorios / 4 ambientes")

    def test_primary_labels_override_recommendation_numbers(self):
        html=page("Casa en Alquiler", "Villa Devoto. Ambientes 3 Dormitorios 2. $ 2.000.000. Sup. total 170 m². Propiedades similares: Casa 4 ambientes 3 dormitorios.")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/48","Test Agency")
        self.assertIsNone(row)
        self.assertEqual(reason,"not 3 dormitorios / 4 ambientes")

    def test_commercial_land_not_eligible(self):
        html=page("4 Lotes con mejoras", "Villa Luro Alquiler $ 1.200.000. 4 ambientes 3 dormitorios. 259 m².")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/49","Test Agency")
        self.assertIsNone(row)
        self.assertEqual(reason,"not residential")

    def test_known_two_bedroom_bener_listing_rejected(self):
        html=page("Casa en Alquiler en Villa Devoto", "Allende 3805 Villa Devoto. Precio alquiler $ 2.000.000 / mes. Sup. total 170 m². Ambientes 3. Dormitorios 2. Baños 2. Cochera 1. Casa en lote propio, 3 ambientes, totalmente amueblada. Propiedades relacionadas Casa 4 ambientes con 3 dormitorios.")
        row,reason=parse_property(html,"https://www.bener.com.ar/casa-en-alquiler-en-villa-devoto-ficha-h-609","Bener")
        self.assertIsNone(row)
        self.assertEqual(reason,"not 3 dormitorios / 4 ambientes")

    def test_generic_search_navigation_is_not_a_rental(self):
        html=page("Buscador de propiedades", "Inicio Contacto Llámenos 4643-0108 Liniers, Capital Federal. Operación Venta Alquiler. Dormitorios 1 2 3 4 5 6. $ 2.500.000. Casa PH Departamentos. Sup. total 140 m².")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/48","Test Agency")
        self.assertIsNone(row)
        self.assertEqual(reason,"generic search page")

    def test_commercial_only_bener_house_rejected(self):
        html=page("Casa de 4 ambientes en Alquiler en Monte Castro, Lascano 5055", "USO COMERCIAL OFICINAS Y DEPOSITO. $ 1.800.000. Ambientes 4. Dormitorios 3. Sup. total 220 m².")
        row,reason=parse_property(html,"https://www.bener.com.ar/casa-en-alquiler-en-monte-castro-ficha-bnr-0016","Bener")
        self.assertIsNone(row)
        self.assertEqual(reason,"commercial-only use")

    def test_real_property_gallery_and_neighborhood(self):
        html='<html><body><main><h1>Casa 4 ambientes en alquiler Monte Castro</h1><p>Lascano 5055 $ 1.800.000. Dormitorios 3. Sup. total 220 m². Contacto oficina Villa Devoto</p><img src="https://example.com/fotos/casa1.webp"><img src="https://example.com/fotos/casa2.jpg"></main></body></html>'
        row,reason=parse_property(html,"https://agency.example.org/propiedad/50","Test Agency")
        self.assertEqual(reason,"eligible")
        self.assertEqual(row["bairro"],"Monte Castro")
        self.assertEqual(len(row["photos"]),2)

    def test_tokkobroker_detail_with_generic_heading(self):
        html=page("Buscador de propiedades", "En alquiler $ 2.300.000 Pasaje Santa Maria al 1600 Monte Castro, Capital Federal. Detalles de propiedad. Ambientes: 5 Dormitorios: 4 Total construido: 198 m². Casa, patio y terraza.")
        row,reason=parse_property(html,"https://www.varcasiapropiedades.com.ar/p/12037797-Casa-en-Alquiler-en-Monte-Castro","Varcasia Propiedades")
        self.assertEqual(reason,"eligible")
        self.assertEqual(row["beds"],4)

    def test_falco_own_listing_with_generic_heading(self):
        html=page("Buscador de propiedades", "En alquiler $ 1.550.000 Bacacay 5609 Villa Luro. Sup. total 70 m². Dormitorios 3 Ambientes 4. Casa con terraza.")
        row,reason=parse_property(html,"https://www.inmofalco.com.ar/propiedad/207797_casa-en-villa-luro/","Inmobiliaria Falco")
        self.assertEqual(reason,"eligible")
        self.assertEqual(row["beds"],3)

    def test_bosich_generic_search_page_rejected_even_if_url_looks_like_property(self):
        html=page("Buscador de propiedades", "Operación alquiler venta. Liniers. Dormitorios 1 2 3 4. $ 2.500.000. Casa 4 ambientes.")
        row,reason=parse_property(html,"https://www.bosichbienesraices.com.ar/propiedad/123-test","Bosich")
        self.assertIsNone(row)

    def test_invalid_phone_not_bedrooms(self):
        html=page("Departamento en alquiler Liniers", "Liniers. $ 750.000. Tel 216892. 2 ambientes. Superficie 80 m².")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/47","Test Agency")
        self.assertIsNone(row)

if __name__=="__main__":
    unittest.main()
