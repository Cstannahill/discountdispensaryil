"""Enumerated extraction failure codes. Free-text errors are classified once, here,
so fallback routing and coverage reports never depend on substring checks elsewhere."""
from enum import Enum
import re


class FailureCode(str, Enum):
    NO_LEAD = 'NO_LEAD'
    LEAD_UNVERIFIED = 'LEAD_UNVERIFIED'
    BRANCH_MISMATCH = 'BRANCH_MISMATCH'
    GATE_AGE_TERMS = 'GATE_AGE_TERMS'
    GATE_LICENSE = 'GATE_LICENSE'
    GATE_UNKNOWN = 'GATE_UNKNOWN'
    CHALLENGE_BLOCKED = 'CHALLENGE_BLOCKED'
    HTTP_REJECTED = 'HTTP_REJECTED'
    TRANSPORT_ERROR = 'TRANSPORT_ERROR'
    RENDER_BLANK = 'RENDER_BLANK'
    SCHEMA_UNKNOWN = 'SCHEMA_UNKNOWN'
    PAGINATION_UNKNOWN = 'PAGINATION_UNKNOWN'
    TOTAL_UNVERIFIABLE = 'TOTAL_UNVERIFIABLE'
    COUNT_MISMATCH = 'COUNT_MISMATCH'
    UNSTABLE = 'UNSTABLE'
    SUSPICIOUS_DROP = 'SUSPICIOUS_DROP'
    DRIFT = 'DRIFT'
    PROVIDER_UNSUPPORTED = 'PROVIDER_UNSUPPORTED'
    RESPONSE_TOO_LARGE = 'RESPONSE_TOO_LARGE'
    INTERRUPTED = 'INTERRUPTED'
    UNKNOWN = 'UNKNOWN'


# code -> (next action, eligible for the third-tier agent)
ACTIONS = {
    FailureCode.NO_LEAD: ('More search channels, chain inference', True),
    FailureCode.LEAD_UNVERIFIED: ('Browser branch selection, then agent', True),
    FailureCode.BRANCH_MISMATCH: ('Rediscover; check rebrand or address alias', False),
    FailureCode.GATE_AGE_TERMS: ('Enable ordinary age/terms handling in browser settings', False),
    FailureCode.GATE_LICENSE: ('Browser license-context handler', True),
    FailureCode.GATE_UNKNOWN: ('Agent learns the unrecognized gate', True),
    FailureCode.CHALLENGE_BLOCKED: ('Report as blocked; no bypass', False),
    FailureCode.HTTP_REJECTED: ('Retry through the ordinary browser tier', False),
    FailureCode.TRANSPORT_ERROR: ('Retry later; network failure is not a store verdict', False),
    FailureCode.RENDER_BLANK: ('Network-first capture, request policy check, then agent', True),
    FailureCode.SCHEMA_UNKNOWN: ('Auto-mapper, then agent', True),
    FailureCode.PAGINATION_UNKNOWN: ('Scroll/pagination discovery', True),
    FailureCode.TOTAL_UNVERIFIABLE: ('Graded completeness (visible counter), else partial offers', False),
    FailureCode.COUNT_MISMATCH: ('Re-traverse; check variant expansion', False),
    FailureCode.UNSTABLE: ('Churn-tolerant reconcile', False),
    FailureCode.SUSPICIOUS_DROP: ('Wait for independent confirmation 60s+ later', False),
    FailureCode.DRIFT: ('Re-learn adapter or recipe', True),
    FailureCode.RESPONSE_TOO_LARGE: ('Document still exceeds the size limit after markup reduction; use network collections or paged capture', True),
    FailureCode.PROVIDER_UNSUPPORTED: ('Build a native contract or use the universal extractor', True),
    FailureCode.INTERRUPTED: ('Retry; worker stopped', False),
    FailureCode.UNKNOWN: ('Inspect evidence and add a classification rule', False),
}

# Order matters: the first matching rule wins.
_RULES = [
    (r'access challenge|just a moment|attention required|captcha', FailureCode.CHALLENGE_BLOCKED),
    (r'worker stopped|interrupted', FailureCode.INTERRUPTED),
    (r'no retailer locator connector|search found no corroborated|no corroborated public menu endpoint', FailureCode.NO_LEAD),
    (r'age/terms confirmation|age gate|age-gate', FailureCode.GATE_AGE_TERMS),
    (r'license-specific|license context|license/source context', FailureCode.GATE_LICENSE),
    (r'conflicts with registry|different street address|different location|different branch|identity_conflict|menu changed branch address', FailureCode.BRANCH_MISMATCH),
    (r'no corroborated matching address|needs matching|did not expose a corroborated|no matching branch', FailureCode.LEAD_UNVERIFIED),
    (r'locator\.click|waiting for getbyrole|shopping context|location selector', FailureCode.GATE_UNKNOWN),
    (r'ssr query cache missing|schema drift|unvalidated .* schema|required source query missing', FailureCode.DRIFT),
    (r'no structured products extracted', FailureCode.RENDER_BLANK),
    (r'redirected to a different source hostname|rediscovery required', FailureCode.DRIFT),
    (r'no stable source identity', FailureCode.SCHEMA_UNKNOWN),
    (r'no independently verifiable|advertises no', FailureCode.TOTAL_UNVERIFIABLE),
    (r'empty_or_large_drop|large_drop', FailureCode.SUSPICIOUS_DROP),
    (r'changed across|changed between|did not reconcile across|menu changed', FailureCode.UNSTABLE),
    (r'missing products|inconsistent (?:advertised )?total|does not reconcile|expected_count_mismatch|missing page products', FailureCode.COUNT_MISMATCH),
    (r'exceeds (?:the )?response size limit|response size limit exceeded', FailureCode.RESPONSE_TOO_LARGE),
    (r'page limit|ambiguous next-page|pagination repeated|pagination changed', FailureCode.PAGINATION_UNKNOWN),
    (r'unsupported (?:menu )?provider|unsupported_provider', FailureCode.PROVIDER_UNSUPPORTED),
    (r'unknown schema|unrecognized (?:schema|response)', FailureCode.SCHEMA_UNKNOWN),
    (r'http (?:401|403|429|451|503)\b|returned http (?:4|5)\d\d|http (?:4|5)\d\d at', FailureCode.HTTP_REJECTED),
    (r'public fetch failed|connecterror|connecttimeout|readtimeout|tls|ssl|name or service|getaddrinfo|rendering did not finish', FailureCode.TRANSPORT_ERROR),
]
_COMPILED = [(re.compile(pattern, re.I), code) for pattern, code in _RULES]
_STATUS_HINTS = {'identity_conflict': FailureCode.BRANCH_MISMATCH, 'blocked': FailureCode.GATE_AGE_TERMS}


def classify(message, *, resolution_status=None):
    """Return the FailureCode for an error string. A resolution status only decides
    when the text itself matches nothing."""
    text = str(message or '')
    for pattern, code in _COMPILED:
        if pattern.search(text):
            return code
    return _STATUS_HINTS.get(resolution_status, FailureCode.UNKNOWN)


def next_action(code):
    return ACTIONS[FailureCode(code)][0]


def agent_eligible(code):
    return ACTIONS[FailureCode(code)][1]
