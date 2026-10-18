import unittest

from backend.platforms import KNOWN, brand_key, detect


class PlatformSignatureTests(unittest.TestCase):
    def test_menu_platform_signatures_are_detected_from_page_text(self):
        cases = {
            '<iframe src="https://www.iheartjane.com/embed/stores/3050/menu"></iframe>': ['jane'],
            '<script src="https://dutchie.com/api/v2/embedded-menu/abc.js"></script>': ['dutchie'],
            '<script>jointEcommerce.currentStore = {"joint_business_id":"1"};</script>': ['joint'],
            '<script>window["__sw_qc"]={}</script>': ['sweed'],
            '<script id="__NEXT_DATA__">{"initialSearchResponse":{}}</script>': ['treez'],
            '<a href="https://api.dispenseapp.com/v1/venues/x">': ['dispense'],
        }
        for text, expected in cases.items():
            self.assertEqual(detect(text), expected, text)

    def test_marketing_widgets_and_plain_pages_are_not_menu_platforms(self):
        self.assertEqual(detect('<script src="https://lab.alpineiq.com/aiq-sdk/widget.js"></script>'), [])
        self.assertEqual(detect('<html><body>Welcome</body></html>'), [])
        self.assertEqual(detect(None), [])

    def test_known_platforms_include_the_native_providers(self):
        self.assertTrue({'jane', 'dutchie', 'joint', 'sweed', 'treez', 'dispense', 'blaze'} <= KNOWN)


class BrandKeyTests(unittest.TestCase):
    def test_branch_suffixes_and_city_names_are_removed(self):
        cases = [
            (('NuEra Pekin', 'Pekin'), 'nuera'),
            (('Nuera East Peoria', 'East Peoria'), 'nuera'),
            (('nuEra Chicago Southland', 'Harvey'), 'nuera chicago southland'),
            (('Terrabis - Dixon', 'Dixon'), 'terrabis'),
            (('Bloom Wellness - Normal', 'Normal'), 'bloom wellness'),
            (('Sunnyside  Naperville', 'Naperville'), 'sunnyside'),
            (('Cloud 9 - East Peoria', 'East Peoria'), 'cloud9'),
            (('Cloud9 - Champaign', 'Champaign'), 'cloud9'),
            (('Pekin Local Dispensary & Supply', 'Pekin'), 'pekin local dispensary supply'),
        ]
        for (name, city), expected in cases:
            self.assertEqual(brand_key(name, city), expected, name)


class ResolutionTaggingTests(unittest.TestCase):
    def test_resolved_endpoints_carry_the_platforms_seen_on_their_page(self):
        from backend.adapters import resolve_menu
        from backend.network import FetchResult
        text = ('<h1>Noxx East Peoria</h1> 300 S Main St East Peoria '
                '<script src="https://dutchie.com/api/v3/embedded-menu/65772a69ac53410009424572/carousels/b.js?routeRoot=https%3A%2F%2Fnoxx.com%2Fstores%2Fnoxx-peoria"></script>')

        class Fetcher:
            browser_options = {'enabled': False}

            def get(self, url, headers=None):
                return FetchResult(url, 200, text.encode(), {}, 'e1', '2026-10-18T09:00:00Z')
        store = dict(name='Noxx - East Peoria', address='300 S Main St', city='East Peoria', state='IL', website='https://noxx.com/location/noxx-peoria/')
        results = resolve_menu(store, Fetcher())
        self.assertTrue(results)
        self.assertTrue(all('dutchie' in r.get('platforms', []) for r in results))


if __name__ == '__main__':
    unittest.main()
