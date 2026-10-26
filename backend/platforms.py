"""Menu-platform signatures and brand keys: which shared platform or chain a store's own pages run on.

The census groups stores so that fixes land per platform or chain rather than per store (docs/PLATFORM_FIRST_PLAN.md).
A signature says a page references a platform; it is not branch identity and never makes an endpoint by itself.
"""
import re

# Menu/commerce platforms only. Marketing, loyalty, chat and analytics widgets (AlpineIQ, Springbig, HighQ, ...) appear
# on many storefronts and say nothing about where the menu comes from, so they are deliberately absent.
SIGNATURES = {
    'carrot': r'getcarrot\.io|carrot-store-root',
    'jane': r'iheartjane\.com|jane-frame|janeroot',
    'dutchie': r'dutchie\.com|dutchieplus',
    'joint': r'jointEcommerce|/wp-content/plugins/joint-ecommerce/',
    'sweed': r'sweedpos\.com|__sw_qc',
    'treez': r'treez\.io|initialSearchResponse|treezStores',
    'dispense': r'dispenseapp\.com',
    'blaze': r'blaze\.me|tymber',
    'meadow': r'getmeadow\.com',
    'posabit': r'posabit',
    'flowhub': r'flowhub',
    'cova': r'covasoftware|cova-ecom',
    'leafly': r'leafly\.com/(?:dispensary-info|shop)',
    'weedmaps': r'weedmaps\.com/dispensar',
}
_COMPILED = {name: re.compile(pattern, re.I) for name, pattern in SIGNATURES.items()}
KNOWN = frozenset(SIGNATURES) | {'cresco'}
_SEPARATOR = re.compile(r'\s+-\s+|\s{2,}|\s+\|\s+')


def detect(text):
    """Sorted platform names whose signature appears in the page text (HTML, embed URLs, or captured request URLs)."""
    if not text:
        return []
    return sorted(name for name, pattern in _COMPILED.items() if pattern.search(text))


def brand_key(name, city=''):
    """A grouping key for a chain: the store name without its branch suffix or trailing city.

    A hint for reports and work queues, never an identity. 'NuEra Pekin' and 'Nuera East Peoria' share 'nuera';
    'Cloud 9 - East Peoria' and 'Cloud9 - Champaign' share 'cloud9'."""
    head = _SEPARATOR.split((name or '').strip())[0]
    text = re.sub(r'[^a-z0-9 ]+', ' ', head.lower())
    text = re.sub(r'\b([a-z]+) (\d+)\b', r'\1\2', ' '.join(text.split()))
    place = ' '.join(re.sub(r'[^a-z0-9 ]+', ' ', (city or '').lower()).split())
    if place and text.endswith(' ' + place):
        text = text[:-len(place) - 1]
    return text.strip()
