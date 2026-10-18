"""Evidence-driven Illinois registry parsing and public location resolution.

The audit CSV is a replay fixture, never a live fallback. Registry membership
does not establish operating status, license identity, or a complete menu.
"""
import csv
import hashlib
import io
import json
import math
import re
from urllib.parse import urlencode

REGISTRY_URL = 'https://public.data.illinois.gov/t/Public/views/DispensaryMap/Map.csv?:showVizHome=no'
REGISTRY_SOURCE_PAGE = 'https://cannabis.illinois.gov/about/locations.html'
_HEADERS = ['Dispensary Name', 'Latitude', 'Longitude', 'Serves Medical Patients', 'BLS Region', 'City', 'Dispensary Name', 'Street Address']


def _coordinates(latitude, longitude):
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (ValueError, TypeError) as exc:
        raise ValueError('Coordinates must be numeric') from exc
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Coordinates are outside valid latitude/longitude bounds')
    return latitude, longitude


def parse_registry(raw: bytes) -> list[dict]:
    """Accept the whole validated source or reject it with a row-level reason.

    Duplicate header positions remain visible in raw.columns/raw.values. Source
    keys are observation identities derived from name and address, not licenses.
    An invalid row rejects the import; callers must retain the previous source.
    """
    try:
        rows = csv.reader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
        headers = next(rows)
    except (UnicodeError, StopIteration, csv.Error) as exc:
        raise ValueError('Registry is not a readable UTF-8 CSV') from exc
    if headers != _HEADERS:
        raise ValueError(f'Unexpected registry schema: {headers!r}')
    result, seen = [], set()
    try:
        for number, values in enumerate(rows, 2):
            if len(values) != len(headers):
                raise ValueError(f'Registry row {number}: expected {len(headers)} columns; received {len(values)}')
            data = {}
            for column, value in zip(headers, values):
                value = value.strip()
                if column in data and data[column] != value:
                    raise ValueError(f'Registry row {number}: duplicate {column} conflict')
                data[column] = value
            for field in ['Dispensary Name', 'Street Address', 'City']:
                if not data[field]:
                    raise ValueError(f'Registry row {number}: missing {field}')
            try:
                latitude, longitude = _coordinates(data['Latitude'], data['Longitude'])
            except ValueError as exc:
                raise ValueError(f'Registry row {number}: {exc}') from exc
            if data['Serves Medical Patients'].lower() not in ('yes', 'no'):
                raise ValueError(f'Registry row {number}: invalid medical service flag')
            identity = [data['Dispensary Name'], data['Street Address'], data['City'], 'IL']
            key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
            if key in seen:
                raise ValueError(f'Registry row {number}: repeated source identity {identity!r}')
            seen.add(key)
            result.append({'source_key': key, 'name': identity[0], 'address': identity[1], 'city': identity[2], 'state': 'IL',
                           'latitude': latitude, 'longitude': longitude, 'serves_medical': data['Serves Medical Patients'].lower() == 'yes',
                           'raw': {'row_number': number, 'columns': headers, 'values': values}})
    except csv.Error as exc:
        raise ValueError(f'Malformed registry CSV near row {rows.line_num}: {exc}') from exc
    if not result:
        raise ValueError('Registry has no rows; an empty source requires review')
    return result


def _payload(response):
    status = getattr(response, 'status_code', 200)
    if status != 200:
        raise ValueError(f'Location service returned HTTP {status}; origin unchanged')
    if isinstance(response, (dict, list)):
        return response
    try:
        return response.json()
    except (ValueError, AttributeError) as exc:
        raise ValueError('Location service returned an invalid JSON response') from exc


def resolve_location(query: str, fetch) -> dict:
    """Resolve an explicit coordinate pair, US ZIP, or unambiguous US city.

    The supplied fetch boundary owns evidence capture. No error chooses a new
    origin. Caching and selection persistence belong to the storage layer.
    """
    query = query.strip()
    if not query or len(query) > 200:
        raise ValueError('Enter a ZIP, city, or latitude,longitude pair')
    pair = re.fullmatch(r'\s*([+-]?[\d.]+)\s*,\s*([+-]?[\d.]+)\s*', query)
    if pair:
        lat, lon = _coordinates(*pair.groups())
        return {'label': f'{lat}, {lon}', 'latitude': lat, 'longitude': lon, 'precision': 'explicit_coordinates', 'source_url': None, 'raw': {'input': query}}
    if re.fullmatch(r'\d{5}(?:-\d{4})?', query):
        url = f'https://api.zippopotam.us/us/{query[:5]}'
        response = fetch(url)
        raw = _payload(response)
        places = raw.get('places', []) if isinstance(raw, dict) else []
        if not places:
            raise ValueError(f'ZIP {query} was not resolved; origin unchanged')
        if raw.get('post code') != query[:5] or raw.get('country abbreviation') != 'US':
            raise ValueError('ZIP response context does not match the requested US ZIP; origin unchanged')
        if len(places) != 1:
            raise ValueError('ZIP has multiple place centroids; select explicit coordinates')
        place = places[0]
        lat, lon = _coordinates(place.get('latitude'), place.get('longitude'))
        label = f"{place.get('place name', query)}, {place.get('state abbreviation', '')} {query[:5]}".strip()
        precision = 'approximate_zip_centroid'
    else:
        url = 'https://nominatim.openstreetmap.org/search?' + urlencode({'q': query, 'format': 'jsonv2', 'countrycodes': 'us', 'limit': 2})
        response = fetch(url)
        raw = _payload(response)
        if not isinstance(raw, list) or not raw:
            raise ValueError(f'Location {query!r} was not resolved; origin unchanged')
        if len(raw) != 1:
            raise ValueError('Location is ambiguous; include a state or use explicit coordinates')
        lat, lon = _coordinates(raw[0].get('lat'), raw[0].get('lon'))
        label = raw[0].get('display_name', query)
        precision = 'approximate_place_centroid'
    return {'label': label, 'latitude': lat, 'longitude': lon, 'precision': precision, 'source_url': url,
            'raw': raw, 'evidence_id': getattr(response, 'evidence_id', None), 'fetched_at': getattr(response, 'fetched_at', None)}


def haversine_miles(latitude_a, longitude_a, latitude_b, longitude_b) -> float:
    """Unrounded great-circle distance using IUGG mean earth radius."""
    a, b = _coordinates(latitude_a, longitude_a), _coordinates(latitude_b, longitude_b)
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3958.761316 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def territory_scope(latitude, longitude, radius_miles) -> dict:
    """Declare source scope without pretending to have authoritative polygons.

    Neighboring states are possible unsupported jurisdictions, not asserted
    intersections. Even an apparently interior origin cannot earn full-circle
    coverage until an authoritative boundary dataset is installed and verified.
    """
    lat, lon = _coordinates(latitude, longitude)
    radius = float(radius_miles)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError('Radius must be a finite positive number')
    return {'supported_jurisdictions': ['IL'], 'unsupported_jurisdictions': ['IA', 'IN', 'KY', 'MI', 'MO', 'WI'],
            'boundary_status': 'not_evaluated', 'coverage_complete': False,
            'origin': {'latitude': lat, 'longitude': lon}, 'radius_miles': radius,
            'limitations': ['Discovery source covers Illinois only. State boundary intersections have not been verified; neighboring jurisdictions may fall within the requested circle and are unsupported.']}
