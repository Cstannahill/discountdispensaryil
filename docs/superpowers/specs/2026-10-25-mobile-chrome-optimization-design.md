# Mobile Space & Chrome Optimization Design Specification

**Date:** 2026-10-25  
**Topic:** Mobile-first Chrome & Screen Real Estate Optimization for TerpScout (`web/`)  
**Status:** Approved  

---

## 1. Context & Motivation

The TerpScout mobile-first web app (`web/`) provides deal discovery for Illinois cannabis across three primary categories: Flower, Concentrate, and Vapes.

Following the initial frontend overhaul, an audit of the mobile user experience revealed two significant screen-space bottlenecks:
1. **Double Sticky Chrome Collision:** Both the top location bar (`LocationControl` at `top-0 z-40`, ~52px) and the category navigation bar (`CategoryGrid` at `top-[53px] z-30`, ~48px) were stuck to the viewport on mobile. The hardcoded `top-[53px]` offset was brittle across different device viewports, and the combined ~100–115px sticky height continuously occupied valuable viewport space during scrolling.
2. **Stacked Mobile Filter Rails:** In `FilterStrip`, the Strain Type pills and Package Size pills stacked into two separate full-width horizontal scroll rows on mobile screens (<640px), pushing the deal cards further down below the fold. In addition, the `Reset` button was hidden on mobile (`hidden sm:inline-flex`), forcing phone users to open the advanced filters drawer to clear active filters.

This design consolidates the sticky chrome into a single, cohesive, ultra-slim command bar, combines the mobile filter pill rails into a single fluid scroll track, and provides immediate mobile filter reset affordances.

---

## 2. Goals & Non-Goals

### Goals
- **Unified Sticky Command Bar:** Merge the mobile category tabs directly into the primary sticky header, eliminating the secondary sticky `<nav>` and the brittle `top-[53px]` offset.
- **Reduced Sticky Footprint:** Lower the total mobile sticky height from ~115px to ~72px, leaving deals as the primary focus on screen.
- **Single-Rail Horizontal Filter Strip:** Condense the Strain Type and Package Size pills into a single horizontal scrolling rail separated by an elegant divider.
- **Mobile 1-Tap Reset:** Surface an instant `✕ Reset` button on mobile in Row 1 when any filter is active.
- **Token Cleanup:** Replace non-standard Tailwind tokens (such as `py-0.2`) with standard Tailwind tokens (`py-0.5`).
- **Responsive Preservation:** Keep the desktop (`lg:`) 3-column layout and experience identical.

### Non-Goals
- Changing the backend deal ranking algorithms or SQL queries.
- Altering the OTD calculation math or Illinois tax preset values.
- Introducing heavy client-side scroll-direction listeners or rubber-band animations that degrade iOS Safari performance.

---

## 3. Architecture & Component Design

```
+--------------------------------------------------------------------------+
| Unified Sticky Header (sticky top-0 z-40, ~72px on mobile, ~50px on lg)  |
|                                                                          |
| Row 1: [🌿 TerpScout]  [📍 Peoria · 50mi ▾]  [Rec|Med]  [🧮 Calc]        |
| Row 2 (Mobile only): [🌿 Flower (12)] [🍯 Conc (8)] [💨 Vapes (15)] [⚡] |
| (Collapsible Location Drawer expands beneath if opened)                  |
+--------------------------------------------------------------------------+
                                     │
+--------------------------------------------------------------------------+
| FilterStrip (Normal scroll flow, glass-card)                             |
|                                                                          |
| Row 1: [ 🔍 Search deals... ]  [⚙ Filters (2)]  [✕ Reset]                |
| Row 2: [All Strains | Indica | Sativa | Hyb] │ [Any Size | 3.5g | 7g...]  |
| (Collapsible Advanced Filters Drawer: Grade, BOGO, Unverified, Stale)    |
+--------------------------------------------------------------------------+
                                     │
+--------------------------------------------------------------------------+
| CategoryGrid (Single active category on mobile, 3 columns on desktop lg) |
|                                                                          |
| [ Deal Card #1 ]  $/g Hero Badge, 1-tap OTD, dispensary menu link        |
| [ Deal Card #2 ]  ...                                                    |
+--------------------------------------------------------------------------+
```

### 3.1. Unified Sticky Header (`web/app/location.tsx` / `web/app/header.tsx`)
- The sticky header renders at `sticky top-0 z-40`.
- **Row 1:** Brand mark (icon + "TerpScout"), location button (`📍 {place} ({radius} mi) ▾`), license switch (`Rec` / `Med`), and calculator button (`🧮`). On small screens (<375px), place names and titles truncate cleanly with `truncate max-w-[120px]`.
- **Row 2 (Mobile only, `lg:hidden`):** A segmented horizontal category rail rendering the category chips (`Flower`, `Concentrate`, `Vapes`, `All`) with item count badges. Clicking a tab updates the active category in `localStorage` and emits a custom DOM event (`terpscout:category-change`) so `CategoryGrid` reacts immediately.
- **Location Drawer:** When toggled open, the drawer drops down directly below Row 2 as an overlay card with GPS detection, Quick Hubs, ZIP input, and radius pills.

### 3.2. Synchronized `CategoryGrid` (`web/app/categories.tsx`)
- Removes the standalone sticky `<nav className="lg:hidden sticky top-[53px] ...">`.
- Listens for `terpscout:category-change` custom events and synchronizes with `localStorage['terpscout.category']`.
- Renders the `.cat-grid` container with `data-active={active}`:
  - On mobile (`<1024px`), CSS hides all non-active category sections.
  - On desktop (`≥1024px`), all 3 category columns display side-by-side.

### 3.3. Condensed Single-Rail Filter Strip (`web/app/filters.tsx`)
- **Row 1 (Search & Actions):**
  - Search input with clear `✕` button and `250ms` debounce / `Enter` submission.
  - `⚙ Filters` drawer button with count badge.
  - `✕ Reset` button: visible on all screen sizes (including mobile) whenever any filter is active (`hasAnyFilter = true`).
- **Row 2 (Single-Rail Pill Strip):**
  - Unifies Strain Type pills (`All Strains`, `Indica`, `Sativa`, `Hybrid`) and Package Size pills (`Any Size`, `0.5g`, `1g`, `3.5g`, `7g`, `14g`, `28g`) in a single horizontal scroll container with `.no-scrollbar`.
  - A subtle vertical divider (`|`) visually segments strain types from package sizes.
- **Filter Count Badge:**
  - Count reflects non-default values (active grade !== 'whole', active size !== 'any', active strain !== '', bogo, stale, unverified).
  - Uses standard Tailwind spacing (`py-0.5 px-1.5`).

### 3.4. Page Coordination (`web/app/page.tsx`)
- Passes category summary chips (`cats.map(c => ({ id: c, label: c, total: results[i].total, color: ACCENT[c] }))`) into the unified header.
- Renders the unified header at the top, followed by `FilterStrip`, summary text, and `CategoryGrid`.

---

## 4. Error Handling & Edge Cases

1. **SSR Hydration:**
   - Active mobile category defaults to `'flower'` on initial render to prevent SSR hydration mismatches.
   - Initial `localStorage` read occurs inside `useEffect`.
2. **Narrow Viewport Safeguards:**
   - On screens as narrow as 320px–360px, flex items in Row 1 use `shrink-0` on buttons and `truncate` on text labels to prevent wrapping into a 3rd line.
3. **Reset Affordance:**
   - Tapping `✕ Reset` clears both URL query params and local search text state, restoring the default view immediately.
4. **Desktop Continuity:**
   - Category row in header is strictly hidden on `lg:` (`lg:hidden`).
   - Desktop view continues to show all 3 category columns concurrently.

---

## 5. Verification Plan

1. **Unit Tests:** `cd web && npm test` — 8/8 tests pass.
2. **Type Check:** `cd web && npm run typecheck` — 0 errors.
3. **Production Build:** `cd web && npm run build` — Next.js build completes with exit code 0.
4. **Backend API Suite:** `.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v` — 19/19 tests pass.
5. **Mobile Viewport Inspection:** Verify responsive styling across mobile (<640px) and desktop (≥1024px) viewports.
