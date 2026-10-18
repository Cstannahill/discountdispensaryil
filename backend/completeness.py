"""Graded completeness. A = reconciled total + stable independent passes (authorizes removals).
B = converged: an independently displayed total or churn-tolerant stable passes (labeled, no A removals).
C = observed without proof. D = nothing usable."""
from html.parser import HTMLParser
import math
import re

MIN_CONVERGED_ITEMS = 25
CONVERGENCE_KINDS = ('visible_counter', 'churn_tolerant')
# Fields allowed to differ between passes without changing product identity.
CHURN_FIELDS = frozenset(('regular_price', 'effective_price', 'price_per_gram', 'available', 'eligible',
                          'exclusion_reasons', 'conditional'))


class _Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden, self.chunks = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.chunks.append(data)


_COUNT = re.compile(r'(?:\bof\s+|\b)(\d[\d,]*)\s+(?:products|items|results|menu items)\b', re.I)


def visible_total(text):
    """Largest product count the page itself displays ("759 products", "of 1,204 results").
    The largest wins so category counts cannot masquerade as the catalog total."""
    parser = _Visible()
    try:
        parser.feed(text or '')
    except Exception:
        return None
    values = []
    for match in _COUNT.finditer(' '.join(parser.chunks)):
        number = int(match[1].replace(',', ''))
        if 0 < number < 1_000_000:
            values.append(number)
    return max(values) if values else None


def counts_reconcile(source_total, observed):
    """Exact, or within 1% for menus large enough that 1% is at least one item."""
    if source_total is None or observed is None:
        return False
    return abs(source_total - observed) <= math.floor(max(source_total, observed) * 0.01)


def churn_tolerant_equal(first, second):
    """Compare two {(source_id, variant_id): normalized item} passes. Live inventory changes
    price and stock between passes; it does not change what a product is. Membership may
    differ by at most 1% of the larger pass (zero for menus under 100 items)."""
    keys_a, keys_b = set(first), set(second)
    membership = len(keys_a ^ keys_b)
    allowed = math.floor(max(len(keys_a), len(keys_b)) * 0.01)
    explained, unexplained = 0, 0
    for key in keys_a & keys_b:
        a = {k: v for k, v in first[key].items() if k != 'raw'}
        b = {k: v for k, v in second[key].items() if k != 'raw'}
        if a == b:
            continue
        changed = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
        if changed <= CHURN_FIELDS:
            explained += 1
        else:
            unexplained += 1
    ok = membership <= allowed and unexplained == 0
    return ok, dict(membership_changes=membership, membership_allowed=allowed,
                    explained_changes=explained, unexplained_changes=unexplained)


def churn_convergence(first, second, *, kind, source_total=None):
    """Convergence claim for two passes of normalized item lists, or None when they do not agree.
    Callers use this only after each pass individually reconciled to its advertised total."""
    a = {(i['source_id'], i['variant_id']): i for i in first}
    b = {(i['source_id'], i['variant_id']): i for i in second}
    if len(a) != len(first) or len(b) != len(second) or len(a) < MIN_CONVERGED_ITEMS:
        return None
    ok, detail = churn_tolerant_equal(a, b)
    if not ok:
        return None
    return dict(kind=kind, passes=2, agreement=True, observed=len(first), source_total=source_total, detail=detail)


def valid_convergence(convergence):
    """A provider's claim of convergence must be well formed before storage trusts it."""
    if not isinstance(convergence, dict):
        return False
    observed = convergence.get('observed')
    return (convergence.get('kind') in CONVERGENCE_KINDS and convergence.get('passes', 0) >= 2 and
            convergence.get('agreement') is True and isinstance(observed, int) and
            not isinstance(observed, bool) and observed >= MIN_CONVERGED_ITEMS)


def grade_for(status, has_items):
    if status == 'complete':
        return 'A'
    if status == 'converged':
        return 'B'
    return 'C' if has_items else 'D'
