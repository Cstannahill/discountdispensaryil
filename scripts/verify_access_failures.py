"""Read-only access diagnostics; never dismisses gates or supplies consent."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.network import PublicFetcher

URLS = [
    'https://risecannabis.com/dispensaries/illinois/',
    'https://highhavencannabis.com/',
    'https://cookies.co/stores/',
    'https://www.verilife.com/',
    'https://beyond-hello.com/illinois-dispensaries/',
    'https://www.trinitydispensaries.com/',
    'https://www.stashdispensaries.com/',
    'https://www.cloud9dispensaries.shop/',
]


def inspect(url):
    fetcher = PublicFetcher(Path('data/evidence/access-verification'), max_attempts=1,
                            timeout_seconds=12, max_run_seconds=30)
    try:
        response = fetcher.get(url)
        body = response.body.decode('utf-8', errors='replace')
        title = re.search(r'<title[^>]*>(.*?)</title>', body, re.S | re.I)
        indicators = [marker for marker in ('cf-chl-', '/cdn-cgi/challenge-platform/',
                       'Just a moment', 'Attention Required', 'please confirm you are at least')
                      if marker.casefold() in body.casefold()]
        result = dict(requested_url=url, final_url=response.url, status=response.status_code,
                      title=html.unescape(title[1]).strip() if title else None,
                      challenge_or_gate_markers=indicators, evidence_id=response.evidence_id,
                      fetched_at=response.fetched_at, body_bytes=len(response.body))
    except Exception as exc:
        causes, current = [], exc
        while current is not None and len(causes) < 6:
            causes.append(type(current).__name__ + ': ' + str(current))
            current = current.__cause__
        result = dict(requested_url=url, error_chain=causes, evidence_id=getattr(exc, 'evidence_id', None))
    finally:
        fetcher.close()
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(inspect, URLS))
    Path('data/access-verification.json').write_text(json.dumps(
        dict(checked_at=datetime.now(timezone.utc).isoformat(), results=results), indent=2)+'\n', encoding='utf-8')
