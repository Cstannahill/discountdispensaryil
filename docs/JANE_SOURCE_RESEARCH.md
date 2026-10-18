# Public Jane and Cloud 9 source research

Observed October 17, 2026. These findings describe public reads and access failures;
they do not establish complete menus or authorize inventory removal. Production
provider adapters are implemented separately in `backend/adapters.py`.

## Evidence and reproduction

Raw responses and manifests are saved under `data/evidence/jane-research/`.
Each identifier below is a manifest SHA-256; its `body_path` identifies the gzip
body. Header values, including publishable storefront keys, are redacted in
diagnostic manifests. Public script bodies are preserved as returned.

Run the read-only probe with the existing Python environment:

```powershell
.venv/Scripts/python.exe scripts/probe_jane_sources.py https://beyond-hello.com/illinois-dispensaries/bloomington/adult-use-menu/
.venv/Scripts/python.exe scripts/probe_jane_sources.py --jane-store 2754
```

The second command reads the captured storefront configuration in
`tests/fixtures/provider_probe/beyond.txt`, never a credential file. It uses the
storefront's published public search configuration. Refresh that capture before
using it to assess a later storefront version. The script never logs key values
for this request. It stops at access failures and does not solve challenges.

## Bloomington: verified provider context, unresolved address/service conflict

The live retailer partner-hosted page returns HTTP 200:

<https://beyond-hello.com/illinois-dispensaries/bloomington/adult-use-menu/>

Evidence: `94635c34e0c16ce6325e8022926882d8cbe7d8b932705344fb7ca48aaddc2e44`.

The `jane_frameless_embed_runtime_config` script specifies Jane `storeId=2754`
and the matching Bloomington adult-use partner path. The same response's public
retailer locator has:

| Field | Retailer observation |
| --- | --- |
| Physical address | 1515 N Veterans Pkwy, Bloomington, IL 61704 |
| Coordinates | 40.5010665, -88.9522343 |
| Medical / recreational | `has_medical=false`, `has_recreational=true` |
| Recreational embed | `https://www.iheartjane.com/embed/stores/2754/menu` |

The Illinois map instead names Bloomington Keaton Place, gives **118 Keaton
Place**, has nearby coordinates **40.5013, -88.95216**, and says medical service
is available. A corner-address alias is plausible but unverified. Preserve this
address and service-context conflict; name/city and nearby coordinates alone
must not establish a license match or invent a medical menu.

The retailer identifies Normal separately: 501 Northtown Road, Normal, with
medical Jane `1633` and recreational Jane `1634`. These are separate branches
and license contexts. The map's Normal coordinate differs from the retailer's;
retain that conflict too.

## Jane API and complete-traversal contract

The runtime settings declare `apiPath=/api/v1`, not `/v1`, and an API host of
`https://api.iheartjane.com`. The actually observed public store route is:

`GET https://api.iheartjane.com/api/v1/stores/2754`

It returned **HTTP 403**, evidence
`1819091d4634d86f563c9ab9e603d1490b2f94b97c3b2205881d7b927ff19e59`.
No authenticated or challenge-bypassing requests were attempted.

The live retailer links `index-BEeT6r0O.js` on the public Boost assets host. Its
referenced menu and product modules were captured:

| Module | Evidence |
| --- | --- |
| `https://boost-assets.iheartjane.com/assets/Menu-_73_3j3w.js` | `e86bf06c449726eadbae0e379b1125574629f23f9a86917f2239e5b5eff0d1f5` |
| `https://boost-assets.iheartjane.com/assets/products-C5j6lFX0.js` | `0bac9d0d1138ad327cd1525558102ad9a172483dcfa7da4f984455f885504e12` |
| `https://boost-assets.iheartjane.com/assets/MenuProductsGrid-Du7dHjFM.js` | `1bf17b4bff3a7b49d98044d1fe8dec8468e907138590bc5e58bb2bc6ffea157a` |

The product module uses Algolia's `searchSingleIndex` with a public app ID,
published search key, the configured `search.iheartjane.com` host, and
`menu-products-production` / `menu-products-by-price-production` indices.
The observed function accepts `filters`, `hitsPerPage`, `page`, categories,
range filters, and search text. An unfiltered store request has this shape:

```http
POST https://search.iheartjane.com/1/indexes/menu-products-production/query
Content-Type: application/json
x-algolia-api-key: <published storefront search key>
x-algolia-application-id: <published storefront app ID>

{"query":"","filters":"store_id:2754","hitsPerPage":100,"page":0}
```

This exact request returned **HTTP 403**, a Cloudflare HTML response titled
`Attention Required!`, evidence
`6d89eafadc07ba025ba52beac3a6d44498f01cc9b4237272bb2fd32f2ca18ea4`.
The response is an access failure, not a zero-product response. No product
total, page count, availability, or live normalization schema was validated.

The public product module declares weight-specific price fields for each,
half gram, gram, two grams, eighth/quarter/half/full ounce; corresponding
discount fields; `net_weight_grams`; `product_id`; `objectID`; `store_id`;
quantity and laboratory fields. These are source-code leads, not evidence that
a live store returned any particular variant. A future adapter must enumerate
all applicable weight variants and check stock/discount semantics using actual
responses before claiming completeness.

[Algolia's primary API documentation](https://www.algolia.com/doc/rest-api/search/search-single-index)
documents response fields `nbHits`, `nbPages`, `hitsPerPage`, `page`, and
`exhaustiveNbHits`. These remain unobserved on this blocked Jane request.
[Algolia's pagination guidance](https://support.algolia.com/hc/en-us/articles/4919156676625-Why-doesn-t-pagination-nbPages-hitsPerPage-match-nbHits)
warns that page limits and reported hit totals can differ. Exhaustiveness must
be reconciled, not inferred from an HTTP 200 or a final advertised page.

`PublicFetcher.post` permits only the two exact Jane search URLs above and the
previously observed GapCommerce product-search URL. Other POST URLs, foreign
header families, and POST redirects are refused. This is not a general write
client.

## Peoria: current-name and operating-status evidence is incomplete

The old retailer URL
`https://beyond-hello.com/illinois-dispensaries/peoria/adult-use-menu/` now
redirects to `https://beyond-hello.com/illinois-dispensaries/` (HTTP 200), evidence
`e4dcb1435c748c759686b2cb7e001e92e9be791bbf8874c0f5e93d51e2aa7406`.
Peoria is absent from the current retailer locator data. Legacy page scripts
still contain an old Peoria route, so a stale route table must not be treated as
proof of a current menu.

An older public Jane embed `https://www.iheartjane.com/embed/stores/6221/menu`
returns a JavaScript shell, evidence
`3facf052d591be60a4dde8c82dab244968881fd7a64578b791b545370649e801`.
This does not corroborate current operating status or any complete menu.

A primary Rise page is discoverable at:

<https://risecannabis.com/dispensaries/illinois/bloom-wellness-peoria/6926/recreational-menu/>

The web reader's copy was crawled three days before this investigation and names
Bloom Wellness Peoria as formerly Beyond Hello. It also displays a temporary
closure notice and 677 product results. Direct public HTTP access returned
**403**, evidence
`e2e193fb3cf870bb737ae4ac9125930df5b9d6c8a3f69f3d8bb3d3d6cc48d37f`.
The reader's dated text is corroboration to investigate, not a persisted live
menu or current confirmed closure. The URL number `6926` has not been validated
as a provider identifier. Preserve the renaming/operating-status uncertainty.

## Cloud 9 East Peoria

The current shop redirects to the `www` host and returns a JavaScript shell:

<https://www.cloud9dispensaries.shop/>

Evidence `abc399489d926fe2d0f7f5976ba374621876301f5413b3d5fd45a4e308397437`.
The actually linked `https://www.cloud9dispensaries.shop/static/js/main.4b5027c9.js`
was captured as `e4bce331dc3244e7081092cab1c71fba788c7660c7464c0874f525ec10ab8763`.

The public bundle configures `https://api.crescolabs.com`, a publishable frontend
key, and the route `p/ordering_apps/op/store-inventory-breakdown`. Its parameters
include `host`, `usage_type`, `store_slug`, and optional location data. Its
HTTP wrapper sends the frontend key with `x-api-key` and may send an initialized
`ordering_app_id` and selected `store_id`. The bundle route alone does not supply
a verified East Peoria tenant, selected-store identifier, product page contract,
or total count. The provider agent's separate public API probe returned 401;
that observation must not be presented as an empty menu.

Additional public menu leads were checked:

| Source | Result | Evidence |
| --- | --- | --- |
| `https://cloud9cannabis.com/east-peoria-menu/` | 403 | `27c6a2e53f7af4e3d31ff7b29a00cfba4817d7038d10c9c34cb1d261c2b6f6fd` |
| `https://cloud9cannabis.com/east-peoria-menu-2/` | 403 | `d972545d68cb4d21db0d7ba10e64b520c5e52baabd041f3612541c9a335d6a22` |
| `https://cloud9eastpeoria.greensling.com/category` | 200; no displayed menu items | `44687e66ec64b24d7e34bf5c10f868303452f59e376c69a550c66dfcfc22b318` |

The Greensling page names **406 W. Camp Street, East Peoria, IL 61611** and
explicitly describes an adult-use dispensary offering a **30% medical-card
discount** using daily state allotments instead of a patient's personal medical
allotment. This corroborates the physical branch and flags the regulator map's
medical-service flag for reconciliation. It does not justify creating a medical
menu. The endpoint's current authority is unverified, so its zero displayed
items cannot authorize a confirmed-empty snapshot or removal.

## Acceptance status

No complete Jane or Cloud 9 menu was captured. These sources must remain
blocked/unsupported/unresolved with dated evidence, address/license conflicts,
and last-attempt outcomes visible. The access failures and uncertain endpoint
authority leave the full regional-menu acceptance criterion unmet.


## Later acquisition verification

The ordinary Phili recreational storefront rendered 759 products after authorized age confirmation in Chrome. Its cards are in an open shadow root; the worker now traverses and serializes those roots. Native Phili/Aces probes exposed capacity saturation and an unbounded LaunchDarkly event stream that prevented capture completion. Those shared defects were corrected, and both probes now finish HTTP 200, but still produce zero product observations. A 30-second readiness probe did not recover Phili. See IMPLEMENTATION_PROGRESS.md, data/jane-shadow-stream-cohort.json and data/jane-bootstrap-budget-probe.json. These new results do not overturn the earlier recorded API rejection or prove that every current blank menu is a CAPTCHA. Native Jane acquisition/full traversal remains unresolved.
