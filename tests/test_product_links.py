import unittest

from backend.product_links import product_url, with_product_url


class ProductLinks(unittest.TestCase):
    def test_sweed(self):
        item = dict(source_id='311200', raw=dict(product=dict(category=dict(canonicalName='pre-rolls', id=4146)), variant=dict(id=405451)))
        self.assertEqual(product_url('sweed', 'https://shop.treehausil.com/morris/menu', 'recreational', item),
                         'https://shop.treehausil.com/morris/menu/pre-rolls-4146/x-405451')
        self.assertIsNone(product_url('sweed', 'https://curaleaf.com/shop/illinois/curaleaf-il-justice/medical/menu', 'medicinal', item))
        self.assertIsNone(product_url('sweed', 'https://shop.example.com/morris', 'recreational', item))

    def test_verano_adds_license_segment(self):
        item = dict(source_id='386053', raw=dict(product=dict(category=dict(canonicalName='drinks', id=6389)), variant=dict(id=581831)))
        self.assertEqual(product_url('verano', 'https://zenleafdispensaries.com/locations/st-charles/menu', 'recreational', item),
                         'https://zenleafdispensaries.com/locations/st-charles/menu/recreational/menu/drinks-6389/x-581831')
        self.assertIn('/medical/menu/', product_url('verano', 'https://zenleafdispensaries.com/locations/st-charles/menu', 'medicinal', item))

    def test_dutchie_and_joint(self):
        self.assertEqual(product_url('dutchie', 'https://dutchie.com/embedded-menu/65772a69ac53410009424572', 'recreational', dict(source_id='6a7c')),
                         'https://dutchie.com/embedded-menu/65772a69ac53410009424572/product/6a7c')
        self.assertEqual(product_url('joint', 'https://terrabis.co/menu/plainfield-il-rec/', 'recreational', dict(source_id='5120a060')),
                         'https://terrabis.co/menu/plainfield-il-rec/?product_page=5120a060')

    def test_unverified_provider_keeps_menu_and_existing_product_urls_win(self):
        self.assertEqual(with_product_url(dict(source_id='1', source_url='https://x.com/menu'), 'jane', 'https://x.com/menu', 'recreational'), 'https://x.com/menu')
        own = 'https://x.com/product/abc'
        self.assertEqual(with_product_url(dict(source_id='1', source_url=own), 'dutchie', 'https://dutchie.com/embedded-menu/ab12', 'recreational'), own)


if __name__ == '__main__':
    unittest.main()
