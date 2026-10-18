"""Render the measured live acceptance JSON into a reviewable coverage report."""
import json
from pathlib import Path


def main():
    report = json.loads(Path('data/live-acceptance-final.json').read_text(encoding='utf-8'))
    counts = report['coverage']['counts']
    lines = ['# Measured live acceptance', '',
             f"Checked at {report['checked_at_utc']}. Region: {report['region']['label']}, {report['region']['radius_miles']} straight-line miles from an approximate ZIP centroid.", '',
             f"Overall run: **{report['job']['status']}**. {counts['known_stores']} registry locations; {counts['fresh_menus']} fresh accepted license-specific menus across four physical stores; {counts['unresolved_menus']} stores without resolved imported menus.", '',
             f"Retained {counts['products']:,} source product identities (counted separately per menu/license), {counts['total_variants']:,} variants, and {counts['eligible_offers']:,} eligible comparable offers. A product appearing in both medical and recreational contexts counts in both menus. These are observed counts, not an estimate of total regional inventory.", '',
             '## Per-location results', '',
             '| Registry location | Miles | Menu result | Most recent relevant evidence/outcome |',
             '|---|---:|---|---|']
    for store in report['stores']['items']:
        outcomes = [r for r in report['job']['results'] if r.get('store_id') == store['id']]
        successes = [r for r in outcomes if r.get('stage') == 'menu' and r.get('status') == 'complete']
        if successes:
            status = '; '.join(f"{e['license_type']}: {e['status']}" for e in store['endpoints'])
            detail = '; '.join(f"{r.get('source_count')} accepted variants" for r in successes)
        else:
            status = store['menu_status']
            detail = '; '.join(dict.fromkeys(str(r.get('error') or r.get('errors') or r.get('status')) for r in outcomes))
        lines.append(f"| {store['name'].replace('|','/')} | {store['distance_miles']:.1f} | {status} | {detail.replace('|','/')} |")
    lines.extend(['', '## Provider validation and remaining work', '',
                  '- Snap Canna Pontiac: observed Blaze tenant and pickup JSON:API pages, 668 records across seven pages, repeated independently. No product seeds.',
                  '- Sweed: public server-rendered query cache and observed full-menu links. Every page verifies store identity, license, requested page, advertised total, variant identity and stable second traversal. Ivy Hall has distinct verified medical/recreational contexts. Tree Haus listing totals can include a repeated parent product with distinct variants; source parents and variants are counted separately.',
                  '- Blank source names are retained with stable source identity and raw evidence, quarantined from rankings. Missing identity, missing pages and changed traversal boundaries reject the snapshot. Unknown categories/mass and conditional prices remain inspectable.',
                  '- Stash Peru: public storefront has an age/terms gate; independently examined GapCommerce product search returned HTTP 403. No validated complete traversal.',
                  '- Cloud 9 East Peoria: registry location is represented. A normal browser executes the site but reaches an age/qualified-patient assertion plus terms/cookie agreement. No assertion was made for the user. Public locator resolution does not yet establish a full branch menu.',
                  '- Beyond/Hello: Normal, Bloomington Keaton Place and Peoria are distinct registry records. Current public locator responses did not corroborate usable branch/menu endpoints. Retailer-versus-registry relocations/rebrands remain unresolved; do not automatically merge an old address or infer a medical menu from a patient discount.',
                  '- Jane and GapCommerce requests examined during research returned access challenges/403. A browser can sometimes complete ordinary JavaScript or provide a legitimate human interaction; reliable unattended ingestion still needs an accessible public contract or authorized feed. No CAPTCHA or gate bypass is implemented.',
                  '- Aroma Hill and some other branches have retailer/registry address conflicts. Preserve those conflicts instead of binding an unrelated default branch. Several sites require stronger branch-link discovery or a browser-backed connector even when they are publicly viewable.',
                  '- Registry completeness and current operating status are unverified. Illinois is the only registry connector; jurisdiction intersections are not computed. Nineteen unresolved stores mean regional best-deal coverage remains unmet.', '',
                  '## Evidence and reproduction', '',
                  '- `data/live-acceptance-final.json`: exact API region, job outcomes, coverage and stores.',
                  '- `data/evidence/`: compressed public responses and capture manifests; snapshots in SQLite retain page/count/error manifests.',
                  '- `tests/fixtures/provider_*`: observed fixtures and independent provider probe results; `data/probes/ivy/` contains the separate Ivy traversal probe.',
                  '- Run `scripts/live_acceptance.py` against the running API to refresh this evidence, then `scripts/write_acceptance_summary.py` to regenerate this document.',
                  '- Tests and browser evidence are summarized in `docs/IMPLEMENTATION_PROGRESS.md`. Passing tests do not imply that inaccessible providers are covered.', ''])
    Path('docs/LIVE_ACCEPTANCE.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
