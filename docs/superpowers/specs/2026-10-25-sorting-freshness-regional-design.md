# Multi-Criteria Sorting, Relative Freshness, Regional Hubs & Back-to-Top Design Spec

**Date:** 2026-10-25  
**Status:** Approved  
**Scope:** Mobile-first web frontend (`web/`), PostgreSQL queries in `web/lib/deals.ts`, API endpoint `web/app/api/v1/deals/route.ts`, and client controls.

---

## 1. Problem Statement & Motivation
TerpScout's Illinois dispensary menu comparison app currently sorts deals strictly by Best $/g (`price_per_gram ASC`). While optimal for bulk value shoppers, consumers have distinct shopping goals:
- Budget shoppers want the lowest total out-of-pocket price.
- Potency seekers prioritize maximum THC concentration.
- Immediate buyers want the closest dispensary distance.
- Bargain hunters want the steepest promotional percentage discounts.

Furthermore:
- Raw timestamps (e.g. `10/25/2026, 4:15 AM`) fail to convey at a glance whether a menu was scraped minutes ago or hours ago.
- The Quick Hubs drawer covers 7 cities, leaving major regions like Metro East/Collinsville, Carbondale, Quad Cities/Moline, Naperville, and Joliet without 1-tap shortcuts.
- Long infinite/paged deal listings on mobile require tedious scrolling to navigate back to the sticky command bar.

---

## 2. Architecture & Design

### 2.1 Multi-Criteria Sorting Engine
#### Supported Sort Criteria
We define the supported sort types in `web/lib/deals.ts`:
```typescript
export const SORT_OPTIONS = ['value', 'price', 'thc', 'distance', 'discount'] as const;
export type SortOption = typeof SORT_OPTIONS[number];
```

#### SQL Ranking Order Clause
In `queryDeals()` within `web/lib/deals.ts`, the `pg` CTE's `ORDER BY` clause inside `row_number() OVER (...)` is determined dynamically based on `q.sort`:
- **`value` (Default — Best $/g):**
  `(j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, round(distance_miles::numeric,3) ASC, id`
- **`price` (Lowest Total Price):**
  `(j->>'effective_price')::numeric ASC NULLS LAST, (j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, id`
- **`thc` (Highest Potency %):**
  `nullif(regexp_replace(j->>'thc_pct', '[^0-9.]', '', 'g'), '')::numeric DESC NULLS LAST, (j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, id`
- **`distance` (Closest Distance):**
  `distance_miles ASC NULLS LAST, (j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, id`
- **`discount` (Biggest % Savings):**
  `CASE WHEN (NULLIF(j->>'regular_price','')::numeric) > (NULLIF(j->>'effective_price','')::numeric) AND (NULLIF(j->>'regular_price','')::numeric) > 0 THEN (((NULLIF(j->>'regular_price','')::numeric) - (NULLIF(j->>'effective_price','')::numeric)) / (NULLIF(j->>'regular_price','')::numeric)) ELSE 0 END DESC NULLS LAST, (j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, id`

#### API & URL State
- `/api/v1/deals` parses `sort` from `req.nextUrl.searchParams` and validates against `SORT_OPTIONS`.
- In `FilterStrip` (`web/app/filters.tsx`), a compact Sort dropdown/select `[ ⇅ Sort: Best $/g ▾ ]` is added.
- In `web/app/page.tsx`, `sp.sort` is validated and passed to `queryDeals()`. Pagination links preserve `sort`.

---

### 2.2 Relative Freshness & Live Indicator
#### Helper Utility (`web/lib/time.ts`)
```typescript
export interface RelativeTimeInfo {
  label: string;       // e.g. "Just now", "25m ago", "2h ago", "1d ago"
  full: string;        // e.g. "10/25/2026, 4:15 AM CDT"
  isLive: boolean;     // true if observed within the last 4 hours
}

export function formatRelativeTime(isoString: string, nowMs = Date.now()): RelativeTimeInfo;
```
- Differences `< 1 min` (including negative clock skew) return `"Just now"` (`isLive: true`).
- Differences `< 60 mins` return `${mins}m ago` (`isLive: true`).
- Differences `< 4 hours` return `${hours}h ago` (`isLive: true`).
- Differences `< 24 hours` return `${hours}h ago` (`isLive: false`).
- Differences `≥ 24 hours` return `${days}d ago` (`isLive: false`).
- Invalid timestamps return `"Recently observed"` with `isLive: false`.

#### Card Component (`web/app/offer-card.tsx`)
- Displays `🟢 Live · Updated {label}` with a CSS pulsing radar indicator if `isLive === true`.
- Displays `Updated {label}` (or amber `Stale · Updated {label}`) if not live.
- Retains full exact timestamp in `title` and `aria-label`.

---

### 2.3 Expanded Regional Quick Hubs (`web/app/location.tsx`)
Expands `QUICK_HUBS` from 7 to 12 balanced geographic targets:
1. Chicago (`60601`)
2. Naperville (`60540`)
3. Joliet (`60431`)
4. Rockford (`61101`)
5. Quad Cities (`61265`)
6. Peoria (`61602`)
7. Normal (`61761`)
8. Champaign (`61820`)
9. Springfield (`62701`)
10. Streator (`61358`)
11. Metro East (`62234`)
12. Carbondale (`62901`)

---

### 2.4 Floating "Back to Top" Action (`web/app/back-to-top.tsx`)
- Client component rendered in `web/app/page.tsx`.
- Listens to window scroll; appears smoothly when `window.scrollY > 400px`.
- Fixed position: `fixed bottom-5 right-5 sm:bottom-6 sm:right-6 z-40`.
- Clicking performs `window.scrollTo({ top: 0, behavior: 'smooth' })`.
- Frosted dark botanical glass pill styling (`bg-slate-900/90 backdrop-blur-md border border-slate-700/80 text-slate-200 hover:text-emerald-300`).

---

## 3. Verification Plan
1. **Unit Tests (`web/lib/deals.test.ts`):**
   - Test `formatRelativeTime()` with positive and negative diffs, hour boundaries, day boundaries, and invalid dates.
   - Test `SORT_OPTIONS` validation and clause mapping.
2. **Build & Typecheck:**
   - `npm run check` (`tsc --noEmit`)
   - `npm test`
   - `npm run build`
   - `python -m unittest discover -s tests`
3. **Subagent Code Review:**
   - Full branch inspection by Senior Code Reviewer.
4. **Push to Remote:**
   - `git push -u origin main`
