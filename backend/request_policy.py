"""Which requests a rendered page may make through the native browser tunnel.

`strict` is the historical rule (GET/HEAD/OPTIONS plus exact read-only search POSTs) and the default.
`platform_reads` additionally lets a page POST to known menu-platform hosts with a bounded JSON body that
is not a GraphQL mutation. `diagnostic_posts` exists only to measure what a blank menu needs; it is never
selected by default. Account, checkout, and mutation requests are refused by every non-strict policy."""
import json
import re
from urllib.parse import urlsplit

POLICIES = ('strict', 'platform_reads', 'diagnostic_posts')
MAX_BODY_BYTES = 64 * 1024
# Registrable domains of menu platforms whose storefronts load or initialise inventory with POST requests.
PLATFORM_FAMILIES = ('iheartjane.com', 'dutchie.com', 'sweedpos.com', 'gapcommerceapi.com', 'dispenseapp.com',
                     'blaze.me', 'treez.io', 'algolia.net', 'algolianet.com')
_DENIED_PATH = re.compile(r'(?:^|[/_-])(?:login|log-in|signin|sign-in|signup|sign-up|register|password|checkout|payment|payments|cart|carts|order|orders|account|accounts|token|oauth|subscribe|newsletter)(?:$|[/_.-])', re.I)
# Analytics and impression beacons are never needed to read a menu; refuse them even on platform hosts.
_TELEMETRY_PATH = re.compile(r'(?:^|/)(?:events?|track(?:ing)?|capture|record|collect|beacon|analytics|metrics|telemetry|log|logs|identify|pixel)(?:$|[/_.-]|\d)', re.I)
_DENIED_OPERATION = re.compile(r'^(?:add|create|update|delete|remove|submit|login|logout|register|checkout|place|apply|set)', re.I)
_MUTATION = re.compile(r'(?:^|[\s}])mutation\b', re.I)
_COMMENT = re.compile(r'#[^\n]*')


def _in_family(host):
    host = (host or '').lower()
    return any(host == domain or host.endswith('.' + domain) for domain in PLATFORM_FAMILIES)


def _operations(body):
    try:
        value = json.loads(body)
    except (TypeError, ValueError):
        return None
    return [item for item in (value if isinstance(value, list) else [value]) if isinstance(item, dict)]


def is_graphql_mutation(body):
    operations = _operations(body)
    if not operations:
        return False
    for operation in operations:
        query = _COMMENT.sub('', str(operation.get('query') or ''))
        if _MUTATION.match(query.strip()) or re.match(r'\s*mutation\b', query, re.I):
            return True
    return False


def _operation_denied(body):
    return any(_DENIED_OPERATION.match(str(operation.get('operationName') or ''))
               for operation in _operations(body) or [])


def decide(policy, *, method, url, body=None, content_type=None, page_url=None, exact_posts=()):
    """Return {allowed, rule, reason} for one browser request."""
    if method in ('GET', 'HEAD', 'OPTIONS'):
        return dict(allowed=True, rule='read', reason='read method')
    if method != 'POST':
        return dict(allowed=False, rule='method', reason=f'{method} is not a read method')
    if not exact_posts:
        from .network import _READ_ONLY_SEARCH_POSTS
        exact_posts = _READ_ONLY_SEARCH_POSTS
    if url in exact_posts:
        return dict(allowed=True, rule='exact_allowlist', reason='observed read-only search endpoint')
    if policy not in POLICIES or policy == 'strict':
        return dict(allowed=False, rule='strict', reason='POST is not an allowlisted read-only search endpoint')
    path = urlsplit(url).path
    if _DENIED_PATH.search(path):
        return dict(allowed=False, rule='denied_path', reason='account, cart, checkout, or order path')
    if policy != 'diagnostic_posts' and _TELEMETRY_PATH.search(path):
        return dict(allowed=False, rule='telemetry', reason='analytics or tracking beacon')
    text = body or ''
    if policy == 'diagnostic_posts':
        # Experiment arm: only account paths and mutations are refused; opaque bodies (binary beacons) pass.
        if is_graphql_mutation(text) or _operation_denied(text):
            return dict(allowed=False, rule='mutation', reason='GraphQL mutation or state-changing operation')
        return dict(allowed=True, rule='diagnostic_posts', reason='diagnostic experiment; not a production policy')
    if len(text.encode('utf-8', errors='ignore')) > MAX_BODY_BYTES:
        return dict(allowed=False, rule='body_size', reason='request body exceeds the bounded size')
    # Beacons and some SDKs send JSON as text/plain; the body, not the header, decides.
    if text and 'json' not in (content_type or '').lower() and _operations(text) is None:
        return dict(allowed=False, rule='content_type', reason='request body is not JSON')
    if is_graphql_mutation(text) or _operation_denied(text):
        return dict(allowed=False, rule='mutation', reason='GraphQL mutation or state-changing operation')
    if _in_family(urlsplit(url).hostname):
        return dict(allowed=True, rule='platform_family', reason='read-shaped JSON POST to a menu platform host')
    return dict(allowed=False, rule='not_platform', reason='POST host is not a known menu platform')
