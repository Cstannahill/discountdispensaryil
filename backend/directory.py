"""Directory-anchored discovery: find a registry store's own website through one geographic directory.

The registry carries no website. Weedmaps' public discovery listings, read per 0.5-degree region tile, give each
listing's coordinates and street address; a listing's detail gives the retailer's own `website` and state license.
A listing matches a registry store only when it is within MATCH_MILES and has the same street number; name tokens only
order qualifying listings. The website is a lead, never a menu: the resolver must still prove the branch on the
retailer's own page, and nothing here creates an endpoint.
"""
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .domain import distance_miles

LISTINGS_URL = 'https://api-g.weedmaps.com/discovery/v1/listings'
DETAIL_URL = 'https://api-g.weedmaps.com/discovery/v1/listings/dispensaries/'
MATCH_MILES = 0.25
TILE_DEGREES = 0.5  # a tile's farthest point is about 22 mi from its center, inside the 30 mi query radius
TILE_RADIUS = '30mi'
PAGE_SIZE = 100
MAX_PAGES = 20
THROTTLE_SECONDS = 1.0
CACHE_HOURS = 72
CACHE_VERSION = 1
_LISTING_FIELDS = ('id', 'slug', 'name', 'type', 'address', 'city', 'state', 'zip_code', 'latitude', 'longitude', 'license_type', 'web_url', 'menu_items_count')
_NOT_WEBSITES = ('facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'youtube.com', 'tiktok.com', 'linktr.ee')

# One process-wide gate: directory requests are serialized and spaced, and a tile is fetched once even when the
# regional and targeted workers ask for it together.
_lock = threading.Lock()
_last_request = [0.0]


def _get(fetcher, url):
    sleeper = getattr(fetcher, 'sleeper', None)
    wait = THROTTLE_SECONDS - (time.monotonic() - _last_request[0])
    if wait > 0 and callable(sleeper):sleeper(wait)
    try:return fetcher.get(url, headers={'accept': 'application/json'})
    finally:_last_request[0] = time.monotonic()


def _cache_path(fetcher, name):
    folder = getattr(fetcher, 'evidence_dir', None)
    return Path(folder) / 'directory-cache' / name if isinstance(folder, (str, Path)) else None


def _cached(fetcher, name):
    memory = getattr(fetcher, '_directory_cache', None)
    if not isinstance(memory, dict):
        memory = {}
        try:fetcher._directory_cache = memory
        except AttributeError:pass
    saved = memory.get(name)
    path = _cache_path(fetcher, name)
    if saved is None and path and path.exists():
        try:saved = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):saved = None
    if saved and saved.get('version') == CACHE_VERSION and time.time() - saved.get('time', 0) < CACHE_HOURS * 3600:
        memory[name] = saved
        return saved
    return None


def _save(fetcher, name, value):
    value = dict(value, version=CACHE_VERSION, time=time.time())
    memory = getattr(fetcher, '_directory_cache', None)
    if isinstance(memory, dict):memory[name] = value
    path = _cache_path(fetcher, name)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
    return value


def tile_for(latitude, longitude):
    return round(latitude / TILE_DEGREES) * TILE_DEGREES, round(longitude / TILE_DEGREES) * TILE_DEGREES


def tile_listings(fetcher, latitude, longitude):
    """Every dispensary listing in the region tile around a point, paged to the advertised total. Raises on any gap."""
    lat, lng = tile_for(latitude, longitude)
    name = f'weedmaps-tile-{lat:.1f}_{lng:.1f}.json'
    with _lock:
        saved = _cached(fetcher, name)
        if saved:return saved
        found, pages, total = {}, [], None
        for page in range(1, MAX_PAGES + 1):
            url = LISTINGS_URL + '?' + urlencode([('filter[plural_types][]', 'dispensaries'), ('filter[bounding_latlng]', f'{lat:g},{lng:g}'),
                                                  ('filter[bounding_radius]', TILE_RADIUS), ('page_size', PAGE_SIZE), ('page', page)])
            response = _get(fetcher, url)
            if response.status_code != 200:raise ValueError(f'Directory listings HTTP {response.status_code}')
            body = response.json()
            rows, advertised = body['data']['listings'], body['meta']['total_listings']
            if not isinstance(advertised, int) or isinstance(advertised, bool) or not isinstance(rows, list):raise ValueError('Directory page has no listing total')
            if total is None:total = advertised
            if advertised != total:raise ValueError('Directory total changed during paging')
            pages.append(dict(url=response.url, evidence_id=response.evidence_id, fetched_at=response.fetched_at, count=len(rows), total=advertised))
            for row in rows:found.setdefault(str(row['id']), dict({key: row.get(key) for key in _LISTING_FIELDS}, evidence_id=response.evidence_id))
            if len(found) >= total:break
            if len(rows) < PAGE_SIZE:raise ValueError(f'Directory paging ended at {len(found)} of {total} listings')
        else:
            raise ValueError('Directory page limit reached')
        return _save(fetcher, name, dict(tile=[lat, lng, TILE_RADIUS], listings=list(found.values()), pages=pages))


def listing_detail(fetcher, slug):
    name = 'weedmaps-listing-' + re.sub(r'[^a-z0-9-]', '_', slug.lower()) + '.json'
    with _lock:
        saved = _cached(fetcher, name)
        if saved:return saved
        response = _get(fetcher, DETAIL_URL + slug)
        if response.status_code != 200:raise ValueError(f'Directory listing HTTP {response.status_code}')
        listing = response.json()['data']['listing']
        detail = {key: listing.get(key) for key in ('website', 'license_number', 'license_type', 'address', 'city', 'state', 'name', 'slug', 'web_url')}
        return _save(fetcher, name, dict(detail=detail, evidence=dict(url=response.url, evidence_id=response.evidence_id, fetched_at=response.fetched_at)))


def street_number(address):
    # A grid address ("4S120 N Route 59") is one number; a unit letter ("6119A East Ave") is not part of it.
    match = re.match(r'\s*(\d+[NSEW]\d+|\d+)[A-Z]?\b', (address or '').upper())
    return match[1] if match else None


def website_url(value):
    """The retailer's own site, or None for empty, social, link-in-bio, directory, or non-web values."""
    from .site_discovery import canonical_menu_url, domain_is, is_directory_url
    value = (value or '').strip()
    if not value or re.match(r'^[a-z][a-z0-9+.-]*:(?!//)', value, re.I):return None
    if not re.match(r'^https?://', value, re.I):value = 'https://' + value
    host = (urlsplit(value).hostname or '').lower()
    if not host or '.' not in host or is_directory_url(value) or any(domain_is(host, domain) for domain in _NOT_WEBSITES):return None
    parts = urlsplit(canonical_menu_url(value))
    # Tracking parameters make one site look like several leads.
    query = [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True) if not re.match(r'utm_|(?:gclid|fbclid|msclkid)$', key, re.I)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def match_listings(store, listings):
    """(matches, near_misses). A match is within MATCH_MILES at the same street number in the same state; name
    tokens order matches and never qualify one. Near-misses are listings within MATCH_MILES at another number."""
    from .site_discovery import business_words, same_state
    number = street_number(store.get('address'))
    if store.get('latitude') is None or store.get('longitude') is None or not number:return [], []
    names = business_words(store.get('name', ''))
    matches, near = [], []
    for listing in listings:
        if listing.get('latitude') is None or listing.get('longitude') is None:continue
        distance = distance_miles(store['latitude'], store['longitude'], listing['latitude'], listing['longitude'])
        if distance > MATCH_MILES or not same_state(listing.get('state'), store.get('state', 'IL')):continue
        found = dict(listing, distance_miles=round(distance, 3), street_number=street_number(listing.get('address')),
                     name_overlap=len(names & business_words(listing.get('name', ''))))
        (matches if found['street_number'] == number else near).append(found)
    order = lambda x: (-x['name_overlap'], x['distance_miles'])
    return sorted(matches, key=order), sorted(near, key=order)


def lookup(store, fetcher):
    """Directory evidence for one registry store: status, website leads (resolver seeds), matches, and near-misses.
    Never raises for directory trouble; a failed directory leaves web search as the resolver's fallback."""
    from .runtime import PipelineInterrupted
    result = dict(source='weedmaps', status='skipped', leads=[], matches=[], rejected=[], error=None)
    if store.get('latitude') is None or store.get('longitude') is None or not street_number(store.get('address')):return result
    try:
        tile = tile_listings(fetcher, store['latitude'], store['longitude'])
        matches, rejected = match_listings(store, tile['listings'])
        result.update(status='unmatched', rejected=[_summary(x) for x in rejected])
        errors = []
        for listing in matches:
            summary = _summary(listing)
            try:
                found = listing_detail(fetcher, listing['slug'])
                detail = found['detail']
                summary.update(website=detail.get('website'), lead_url=website_url(detail.get('website')), license_number=detail.get('license_number'),
                               license_type=detail.get('license_type'), detail_evidence_id=found['evidence']['evidence_id'], detail_url=found['evidence']['url'])
            except PipelineInterrupted:raise
            except Exception as exc:
                summary.update(error=str(exc), detail_evidence_id=getattr(exc, 'evidence_id', None));errors.append(str(exc))
            result['matches'].append(summary)
        for summary in result['matches']:
            if summary.get('lead_url') and summary['lead_url'] not in [lead['url'] for lead in result['leads']]:
                result['leads'].append(dict(url=summary['lead_url'], status='candidate', source_role='directory', evidence=[summary],
                                            reason='Website named by a Weedmaps listing at the registry street number; branch identity is still required'))
        if result['leads']:result['status'] = 'matched'
        elif matches:result.update(status='failed' if len(errors) == len(matches) else 'no_website', error='; '.join(errors) or None)
    except PipelineInterrupted:raise
    except Exception as exc:
        result.update(status='failed', error=str(exc), evidence_id=getattr(exc, 'evidence_id', None))
    return result


def _summary(listing):
    return dict(source='weedmaps', listing_id=listing.get('id'), slug=listing.get('slug'), name=listing.get('name'), address=listing.get('address'),
                city=listing.get('city'), listing_url=listing.get('web_url') or 'https://weedmaps.com/dispensaries/' + str(listing.get('slug')),
                distance_miles=listing.get('distance_miles'), street_number=listing.get('street_number'), name_overlap=listing.get('name_overlap'),
                menu_items_count=listing.get('menu_items_count'), listing_evidence_id=listing.get('evidence_id'))
