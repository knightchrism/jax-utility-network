"""Guards for the public demo brand: navy/gold chrome, contact, no repo links."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DISCLOSURE = (
    "Water, sewer, and electric distribution networks are <b>SYNTHETIC</b>. "
    "Streets (TIGER), parcels (FDOR), hydrants (COJ/JEA), transmission (HIFLD), "
    "OSM power, septic phase-out areas, and DEM (3DEP) are real."
)
LANDING_NOTE = (
    "Water distribution, gravity sewer and electric distribution networks are <b>synthetic</b>"
)


def map_chrome():
    mod = ast.parse((ROOT / "src/jaxnet/analyze.py").read_text())
    for node in mod.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MAP_CHROME":
                    return ast.literal_eval(node.value)
    raise AssertionError("MAP_CHROME missing from analyze.py")


class BrandingTests(unittest.TestCase):
    def test_landing_pages_match_and_use_site_brand(self):
        index = (DOCS / "index.html").read_text()
        overview = (DOCS / "overview.html").read_text()
        self.assertEqual(index, overview)
        for text in (index, overview):
            self.assertIn("https://geoknightgis.com/", text)
            self.assertIn("mailto:info@geoknightgis.com", text)
            self.assertIn('class="mark" aria-hidden="true">GK</span>', text)
            self.assertIn("--navy:#0b1f3a", text)
            self.assertIn("--gold:#d4a72c", text)
            self.assertIn("--gold2:#f0c75a", text)
            self.assertIn('--ui:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif', text)
            self.assertIn('--display:"Plus Jakarta Sans","Inter",system-ui,sans-serif', text)
            self.assertIn("https://geoknightgis.com/assets/fonts/inter-latin.woff2", text)
            self.assertIn("https://geoknightgis.com/assets/fonts/jakarta-latin.woff2", text)
            self.assertNotIn("#c9a227", text)
            self.assertNotIn("#e6c35c", text)
            self.assertIn(LANDING_NOTE, text)
            self.assertIn("Open interactive map", text)
            self.assertIn('href="map.html"', text)
            self.assertIn("2,789 + 2,671", text)
            self.assertIn("WM00645", text)
            self.assertIn("FU0004", text)
            self.assertIn("12.8%", text)
            self.assertNotIn("github.com", text.lower())
            self.assertNotIn("insured", text.lower())
            self.assertNotIn("#2fb5a8", text)
            self.assertNotIn("#f2a541", text)
            self.assertIn('src="data:image/jpeg;base64,', text)

    def test_map_copies_share_generator_chrome(self):
        chrome = map_chrome()
        docs_map = (DOCS / "map.html").read_text()
        web_map = (ROOT / "web/index.html").read_text()
        self.assertEqual(docs_map, web_map)
        for text in (docs_map, web_map):
            self.assertIn(chrome, text)
            self.assertIn("font-size:13px", chrome)
            self.assertNotIn("font-size:.8125rem", chrome)
            self.assertEqual(text.count('class="gk-home"'), 1)
            self.assertIn(DISCLOSURE, text)
            self.assertIn("https://geoknightgis.com/", text)
            self.assertIn("mailto:info@geoknightgis.com", text)
            self.assertIn("#0b1f3a", text)
            self.assertIn("#d4a72c", text)
            self.assertIn("#f0c75a", text)
            self.assertIn("Plus Jakarta Sans", text)
            self.assertIn("https://geoknightgis.com/assets/fonts/inter-latin.woff2", text)
            self.assertNotIn("#c9a227", text)
            self.assertNotIn("#e6c35c", text)
            self.assertIn('"collapsed": false', text)
            self.assertIn('return {"color": "#38bdf8", "weight": 2}', text)
            self.assertIn("<html lang=\"en\">", text)
            self.assertIn("<title>GeoKnight GIS · Jacksonville Utility Network</title>", text)
            self.assertNotIn("github.com", text.lower())
            self.assertNotIn("color:#38bdf8'>GeoKnight", text)
            self.assertNotIn("insured", text.lower())

    def test_generator_still_writes_branded_map(self):
        source = (ROOT / "src/jaxnet/analyze.py").read_text()
        self.assertIn("folium.Element(MAP_CHROME)", source)
        self.assertIn("folium.LayerControl(collapsed=False)", source)
        self.assertIn("_brand_saved_map(WEB / \"index.html\")", source)
        self.assertNotIn("#38bdf8'>GeoKnight", source)


if __name__ == "__main__":
    unittest.main()
