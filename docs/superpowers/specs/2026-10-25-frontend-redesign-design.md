# TerpScout Mobile-First Web Redesign & Legacy Frontend Retirement — Design Specification

**Date:** 2026-10-25
**Target Branch:** `main`
**Scope:** Redesign `web/` (Next.js Vercel public app at `discountdispensaryil.vercel.app`) for a modern, mobile-first botanical aesthetic and intuitive deal-hunting UX; add strain-type, package-size, and Out-The-Door (OTD) calculator capabilities; relocate Playwright to `web/`; and retire the legacy `frontend/` directory.

---

## 1. Context & Goals

### Problem Statement
1. **Above-the-Fold Mobile Clutter:** In `web/app/page.tsx`, mobile visitors face a tall expanded `LocationControl` card (~240px) plus a 6-field `<form method="get">` filter card (~300px) before seeing a single deal—consuming over 550px of vertical height even after a location is already configured.
2. **Dated Form Ergonomics:** Filters rely on native `<select>` dropdowns, raw checkboxes, and a manual **Apply** submit button (triggering full-page reloads) instead of thumb-friendly, auto-applying pill rails and sheets. Small input font sizes (`text-xs` / `12px`) also trigger involuntary viewport zoom in iOS Safari.
3. **Sub-optimal Mobile Category Default:** `CategoryGrid` (`web/app/categories.tsx`) defaults to `'all'` on mobile, stacking 20 Concentrate cards, 20 Flower cards, and 20 Vape cards in a single 60-card vertical scroll.
4. **Missing Deal-Discovery Controls:** `web/lib/deals.ts` has partial support for `strain_type`, and the backend supports $\pm 3\%$ package-size bucket filtering (`1g`, `3.5g`, `7g`, `14g`, `28g`), but neither is exposed in `web/`. Shoppers also lack an Out-The-Door (OTD) tax and discount calculator on the hosted site.
5. **Typography & Card Hierarchy:** `web/app/layout.tsx` does not load Google Fonts (`Plus Jakarta Sans` / `Inter` and `JetBrains Mono`), causing fallback to `system-ui`. `OfferCard` uses flat boxes, small text (`10px`–`12px`), plain-text strain labels, and an understated text link for the dispensary menu CTA.
6. **Legacy `frontend/` Maintenance Burden:** `frontend/` is an older local Vite UI from before the hosted Next.js site. Only `frontend/node_modules/playwright` is still used by `backend/browser_worker.cjs`.

### Goals
- Compress the mobile above-the-fold chrome so deals appear immediately on screen.
- Deliver a cohesive, high-contrast **Botanical Dark Theme** with `Plus Jakarta Sans` + `JetBrains Mono` typography, category accents, and semantic strain badges.
- Provide instant, thumb-friendly filtering for **License (`Rec` / `Med`)**, **Category**, **Strain Type (`Indica` / `Sativa` / `Hybrid`)**, **Package Size (`Any`, `0.5g`, `1g`, `3.5g`, `7g`, `14g`, `28g`)**, **Flower Grade**, and **Promotions/Freshness**.
- Add an **Out-The-Door (OTD) & Illinois Tax Calculator** accessible both from the top bar and via a 1-tap `🧮 OTD` button on every deal card (pre-filling that card's price, mass, and category tax preset).
- Move `playwright` into `web/package.json` and cleanly remove `frontend/`.

---

## 2. Visual Theme & Typography (`web/app/layout.tsx`, `web/app/globals.css`, `web/tailwind.config.cjs`)

### Typography
- Load `Plus Jakarta Sans` (`--font-sans`, weights 400, 500, 600, 700, 800) and `JetBrains Mono` (`--font-mono`, weights 400, 500, 600, 700) via `next/font/google` in `web/app/layout.tsx`.
- Configure `tailwind.config.cjs` so `font-sans` uses `var(--font-sans)` and `font-mono` uses `var(--font-mono)`.
- **Mobile Input Safety:** All `<input>` and `<select>` elements use `text-base sm:text-sm` (`16px` on mobile) to prevent iOS Safari auto-zoom on focus, with minimum `44px` touch target height where interactive.

### Color & Surface System
- **Background Canvas:** `#060a0d` with a subtle top radial gradient (`radial-gradient(ellipse 80% 50% at 50% -10%, rgba(16, 185, 129, 0.12), transparent)`).
- **Elevated Glass Cards (`.glass-card`):** `rgba(13, 21, 27, 0.88)` with `backdrop-filter: blur(14px)` and `1px solid rgba(255, 255, 255, 0.08)` border.
- **Category Accents:**
  - `flower`: `#34d399` (Emerald)
  - `concentrate`: `#fbbf24` (Amber Gold)
  - `vapes`: `#c084fc` (Electric Violet)
- **Strain Semantic Badges:**
  - `Indica`: `bg-purple-500/15 text-purple-300 border-purple-500/30`
  - `Sativa`: `bg-amber-500/15 text-amber-300 border-amber-500/30`
  - `Hybrid`: `bg-emerald-500/15 text-emerald-300 border-emerald-500/30`
  - `Unspecified`: `bg-slate-800/80 text-slate-400 border-slate-700/60`

---

## 3. Component Architecture (`web/app/`)

### 3.1 Sticky Command Header & Location Sheet (`web/app/location.tsx`)
- **Compact Sticky Bar:**
  - **Brand Identity:** Botanical leaf/drop SVG icon + `TerpScout` title + subtle `$/g Engine · v{data_version}` subtitle.
  - **Interactive Location Pill:** Displays `📍 {place} · {radius} mi ▾` when a location or region is active (or `📍 Set Location ▾` if none). Tapping opens the Location Drawer/Popover.
  - **License Segmented Toggle (`Rec` | `Med`):** Instant 1-tap toggle updating `license=recreational` or `license=medicinal` in the URL.
  - **OTD Calculator Trigger (`🧮 OTD`):** Opens the Calculator modal/sheet.
- **Location Popover / Sheet:**
  - When expanded (or automatically shown inline if no location/region is available), provides:
    1. **`📍 Use my current location`** (browser GPS with clear error/loading states).
    2. **ZIP or City, ST lookup form** (`/api/v1/geocode`).
    3. **Quick Illinois Hub Presets:** `Peoria (61602)`, `Normal (61761)`, `Champaign (61820)`, `Springfield (62701)`, `Chicago (60601)`, `Rockford (61101)`, `Streator (61358)`.
    4. **Search Radius Selector:** Pill buttons for `5`, `10`, `25`, `50`, `100`, `200` miles (persisted to `localStorage` under `terpscout.radius` and URL `radius`).
    5. **Reset button** when a custom GPS/ZIP origin is active.

### 3.2 Instant Filter Strip (`web/app/filters.tsx`)
- Client component synchronizing filter state with URL search params via `useRouter` and `useTransition` (with a subtle pending spinner/progress bar so transitions feel instantaneous).
- **Row 1 — Search & Advanced Filters Button:**
  - Debounced search input (`q`, 250ms debounce + immediate Enter submit + `✕` clear button) with placeholder `"Search strain, brand, or dispensary…"`.
  - **`Filters` Drawer/Popover Trigger:** Shows active count badge when non-default filters are active (`grade !== 'whole'`, `promo === 'bogo'`, `stale`, `unverified`). Inside the popover:
    - **Flower Grade:** Pill selector for `Whole Flower` (`whole`), `Smalls & Popcorn` (`smalls`), `Shake & Ground` (`shake`), `Infused` (`infused`), `All Grades` (`all`).
    - **Deal Scope Toggles:**
      - `BOGO promotions only` (`promo=bogo`)
      - `Include unverified totals (Grade B)` (`unverified=1`)
      - `Include stale menus (>12h)` (`stale=1`)
    - **`Reset all filters`** action when any filter is non-default.
- **Row 2 — Horizontal Quick-Filter Pill Rails:**
  - **Strain Type Rail:** `All Strains` (`''`), `Indica`, `Sativa`, `Hybrid` (color-coded when active).
  - **Package Size Rail:** `Any Size` (`any`), `0.5g`, `1g`, `3.5g (⅛)`, `7g (¼)`, `14g (½)`, `28g (1 oz)`.

### 3.3 Mobile-First Category Navigation (`web/app/categories.tsx`)
- Below `lg` (`< 1024px`), renders a sticky category tab bar at the top of the deals area:
  - Defaults to **`flower`** on mobile (instead of `'all'`), while restoring the user's choice from `localStorage` (`terpscout.category`).
  - Tabs: `Flower`, `Concentrate`, `Vapes`, `All (Split)`.
  - Each tab displays its category label, live total count badge, and category-colored active indicator (`#34d399`, `#fbbf24`, `#c084fc`).
- At `lg` (`>= 1024px`), all 3 category columns render side-by-side in a 3-column grid regardless of the mobile tab state.

### 3.4 Deal Cards & Grouped Strain List (`web/app/offer-card.tsx`)
- **Card Header:**
  - Left: Brand name eyebrow + Product Title (`{brand} · {variants.length} strains` when grouped, or `{name}` when single) + badges row:
    - Semantic **Strain Badge** (`Indica` / `Sativa` / `Hybrid`) for single offers.
    - **Flower Grade Badge** (`smalls`, `shake`, `infused`) when applicable.
    - **THC Badge** (`THC {thc_pct}%`) when present.
    - **Package Weight Badge** (`{weight_label || weight_grams + 'g'}`).
  - Right (Hero Price Block):
    - Primary metric: **`{money(price_per_gram)}`** in `text-xl font-extrabold font-mono text-emerald-400` + `<span className="text-xs text-slate-400">/g</span>`.
    - Secondary price: **`{money(effective_price)}`** total package price (with strikethrough `{money(regular_price)}` when `regular_price > effective_price`).
- **Store & Observation Metadata:**
  - Dispensary name + distance badge (`{distance_miles.toFixed(1)} mi`) + license pill (`rec` / `med`) + freshness/completeness badge (`fresh`, `stale`, or `unverified total` for Grade B) + observed timestamp (`Observed {when(last_seen_at)}`) + `Conditional promotion` tag if `conditional`.
- **Grouped Strain Accordion (`StrainList`):**
  - When `variants.length > 1`, displays an interactive `<details>` accordion styled as a tactile chip (`🌿 {variants.length} strains at this price — Show strains`).
  - Groups variants by `Indica`, `Sativa`, `Hybrid`, `Unspecified` using color-coded group headers, showing each strain name, THC %, and direct dispensary product link (`↗`).
- **Card Actions Footer:**
  - **`View on Menu ↗`:** Prominent button linking to `safeUrl(o.source_url)`.
  - **`🧮 OTD` Button:** Opens the Out-The-Door Calculator pre-populated with this offer's price, weight in grams, category, THC %, and title.

### 3.5 Out-The-Door (OTD) & Illinois Tax Calculator (`web/app/calculator.tsx`)
- Modal / bottom-sheet dialog manageable via a lightweight context or custom event so both the header button and any `OfferCard` can open it with optional pre-filled offer data.
- **Fields:**
  - `Menu Price ($)`
  - `Package Mass (g)` + quick preset chips (`0.5g`, `1g`, `3.5g`, `7g`, `14g`, `28g`)
  - `Discount (%)` + quick preset chips (`0%`, `10%`, `15%`, `20%`, `25%`, `30%`)
  - `Estimated Tax (%)` + **Illinois Tax Presets**:
    - `Medical (~1%)` → `1%`
    - `Rec Flower / ≤35% THC (~22%)` → `22%`
    - `Rec Vape / Infused (~32%)` → `32%`
    - `Rec Concentrate / >35% THC (~37%)` → `37%`
- **Auto-Preset Selection on Pre-fill:** When opened from an `OfferCard`:
  - If `license_type === 'medicinal'`, defaults tax preset to `1%`.
  - Else if `category === 'concentrate'` or `Number(thc_pct) > 35`, defaults tax preset to `37%`.
  - Else if `category === 'vapes'` or `flower_grade === 'infused'`, defaults tax preset to `32%`.
  - Else defaults tax preset to `22%`.
- **Live Output Cards:**
  - `Discounted Pre-Tax $/g`
  - `Estimated Out-The-Door Total`
  - `Estimated Out-The-Door $/g`

---

## 4. Data & API Layer Changes (`web/lib/deals.ts`, `web/app/api/v1/deals/route.ts`)

### 4.1 Package Size Filtering (`size`)
- Export `SIZES = ['any', '0.5', '1', '3.5', '7', '14', '28'] as const` in `web/lib/deals.ts`.
- Add `size?: string` to `DealQuery`.
- In `queryDeals(q)`:
  - When `q.size && q.size !== 'any'` and `Number.isFinite(Number(q.size)) && Number(q.size) > 0`:
    - Add SQL `WHERE` condition matching `backend/storage.py`:
      ```sql
      abs((NULLIF(j->>'weight_grams','')::numeric) - $N::numeric) <= ($N::numeric * 0.03)
      ```
  - In `web/app/page.tsx`:
    - Flower-specific large weights (`3.5`, `7`, `14`, `28`) apply to the `flower` category query; small weights (`0.5`, `1`) apply to all categories (or if a user is filtering by `size`, apply `size` to categories where that weight exists—specifically `0.5` and `1` apply to `concentrate`, `flower`, `vapes`, while `3.5`, `7`, `14`, `28` apply to `flower` and `concentrate` so `vapes` isn't zeroed out when viewing all columns, or apply `size` across the board when explicitly selected). Applying `3.5`/`7`/`14`/`28` only to `flower` (and `0.5` to `concentrate`/`vapes`, `1` to all) when viewing all 3 columns keeps every column useful, while `/api/v1/deals?size=X` applies `size` directly to whatever query is requested.
    - Let's make `size` in `queryDeals` apply whenever `q.size` is passed, and in `page.tsx`:
      - If `size` is `'3.5' | '7' | '14' | '28'`, pass `size` to `flower` (and `concentrate` only if `<= 7`, or pass `size` to `flower` specifically as in `frontend/src/deals.tsx`: `size: category === 'flower' ? size : undefined`, EXCEPT if `size` is `'0.5'` or `'1'`, pass it to all categories!). Wait—even simpler and more predictable: if a user selects `0.5g` or `1g`, pass `size` to all categories; if they select `3.5g`, `7g`, `14g`, or `28g` (standard flower weights), pass `size` to `flower` so Concentrate and Vapes columns still show their best deals instead of "No comparable offers"! And on the Flower column header, display a badge showing the active size filter (e.g. `3.5g`).

### 4.2 Bucket-Consistent Strain Type Filtering (`strain_type`)
- Export `STRAINS = ['Indica', 'Sativa', 'Hybrid'] as const` in `web/lib/deals.ts`.
- In `queryDeals(q)`:
  - Replace the exact match `lower(coalesce(j->>'strain_type',''))=$N` with bucket-consistent matching that aligns with `strainBucket()`:
    - `indica`: `position('indica' in lower(coalesce(j->>'strain_type',''))) > 0`
    - `sativa`: `position('sativa' in lower(coalesce(j->>'strain_type',''))) > 0 AND position('indica' in lower(coalesce(j->>'strain_type',''))) = 0`
    - `hybrid`: `position('hybrid' in lower(coalesce(j->>'strain_type',''))) > 0 AND position('indica' in lower(coalesce(j->>'strain_type',''))) = 0 AND position('sativa' in lower(coalesce(j->>'strain_type',''))) = 0`
  - Pass `strain_type` from `page.tsx` and `/api/v1/deals/route.ts`.

---

## 5. Retiring `frontend/` & Relocating Playwright

1. **`web/package.json`:** Add `"playwright": "^1.58.2"` (matching the installed Playwright version in `frontend/node_modules/playwright`) to `devDependencies` and install via `npm install` in `web/`.
2. **`backend/browser_worker.cjs`:** Update line 3 from:
   ```js
   const { chromium } = require('../frontend/node_modules/playwright');
   ```
   to:
   ```js
   const { chromium } = require('../web/node_modules/playwright');
   ```
3. **`docs/site-maps/raw/batch-5/tools/survey.cjs`:** Update the Playwright require path to point to `web/node_modules/playwright`.
4. **`backend/main.py`:** Remove lines 363–379 (`build = BASE_DIR / "frontend/dist"` static mounts and catch-all route), leaving `/api/v1/*`, `/wyvrn/Synapse`, and `/reference/legacy-demo`.
5. **Delete `frontend/`:** Remove the `frontend/` directory completely.
6. **Documentation & Ignore Files:** Update `CLAUDE.md`, `README.md`, and `.gitignore` to reflect `web/` as the sole frontend and remove `frontend/` references.

---

## 6. Verification & Testing Plan

1. **Unit Tests (`web/lib/deals.test.ts`):**
   - Test `strainBucket` and SQL generation/filtering behavior for `strain_type` (`Indica`, `Sativa`, `Hybrid` with dominant-leaning strings) and `size` ($\pm 3\%$ weight tolerance).
   - Test `parseOrigin` and OTD calculator arithmetic helper functions.
2. **Typecheck & Production Build (`web/`):**
   - Run `npm run typecheck`, `npm test`, and `npm run build` in `web/`.
3. **Backend & Playwright Integration (`tests/`):**
   - Run `.venv\Scripts\python.exe -m unittest discover -s tests -v`.
   - Run `$env:TERPSCOUT_BROWSER_TEST='1'; .venv\Scripts\python.exe -m unittest discover -s tests -p test_browser_render.py -k test_dom_observations_use_unambiguous_sale_price_and_fractional_mass -v` to verify `backend/browser_worker.cjs` resolves `playwright` from `web/node_modules/playwright`.
