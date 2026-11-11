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

    def test_invalid_phone_not_bedrooms(self):
        html=page("Departamento en alquiler Liniers", "Liniers. $ 750.000. Tel 216892. 2 ambientes. Superficie 80 m².")
        row,reason=parse_property(html,"https://agency.example.org/propiedad/47","Test Agency")
        self.assertIsNone(row)

if __name__=="__main__":
    unittest.main()
