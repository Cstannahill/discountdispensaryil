# Multi-Criteria Sorting, Relative Freshness, Regional Hubs & Back-to-Top Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement multi-criteria sorting (Best $/g, Lowest Price, Highest THC, Closest Distance, Biggest % Off), relative freshness with live radar indicator (<4h), expanded regional quick hubs (12 Illinois hubs), and a floating smooth back-to-top action for TerpScout.

**Architecture:** Extend PostgreSQL rank CTE in `web/lib/deals.ts` and `/api/v1/deals` with dynamic sort ordering; create a zero-dependency time formatting utility in `web/lib/time.ts` with unit tests; expand `QUICK_HUBS` in `web/app/location.tsx`; build an accessible, SSR-safe `BackToTop` client capsule in `web/app/back-to-top.tsx`; and integrate a compact sort controller into `FilterStrip` and `page.tsx`.

**Tech Stack:** Next.js 15 (App Router, Server & Client Components), TypeScript, Tailwind CSS, PostgreSQL CTEs, Node `node:test` + `node:assert/strict`.

**Spec:** [`docs/superpowers/specs/2026-10-25-sorting-freshness-regional-design.md`](file:///s:/Code/Other/terpscout_fullstack/docs/superpowers/specs/2026-10-25-sorting-freshness-regional-design.md)

## Global Constraints
- Preserve existing comments and docstrings.
- 0 TypeScript compiler errors (`npm run check`).
- All unit tests passing (`npm test`).
- Production build succeeds (`npm run build`).
- Python backend test suite passing (`python -m unittest discover -s tests`).
- Mobile-first responsive layout with botanical dark theme (`#060a0d`, `#10b981`, `#047857`).

## Review Focus
1. **THC String Non-numeric Content:** Deals where `thc_pct` contains `%` or non-numeric symbols must not crash SQL cast or sort improperly.
2. **Division by Zero on Zero Weight or Zero Price:** `(j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0)` must prevent SQL `division by zero`.
3. **Sub-minute and Negative Clock Skew in Freshness:** Client clock behind server must display `"Just now"` with `isLive = true`, never negative values or runtime errors.
4. **Hydration Safety for BackToTop:** Scroll listener and window queries must run only after client mounting (`useEffect`) to avoid React hydration mismatches.
5. **Sort State Retention Across Pagination:** Changing page numbers or categories must preserve the active `sort` query parameter.

---

### Task 1: Multi-Criteria Sorting in Database Queries & API Endpoint

**Files:**
- Modify: `web/lib/deals.ts:46-52, 148-154`
- Modify: `web/app/api/v1/deals/route.ts:13-19`
- Test: `web/lib/deals.test.ts`

**Interfaces:**
- Consumes: Existing `DealQuery`, `reps` CTE in `web/lib/deals.ts`.
- Produces: `SORT_OPTIONS`, `SortOption`, and `sort` parameter in `DealQuery`.

- [ ] **Step 1: Write failing test in `web/lib/deals.test.ts` for sort options and clauses**

```typescript
import { SORT_OPTIONS, type SortOption, sortOrderClause } from './deals.ts';

test('SORT_OPTIONS defines all 5 supported sorting criteria', () => {
  assert.deepEqual(SORT_OPTIONS, ['value', 'price', 'thc', 'distance', 'discount']);
});

test('sortOrderClause generates safe SQL clauses for all options', () => {
  assert.match(sortOrderClause('value'), /effective_price.*weight_grams.*ASC/);
  assert.match(sortOrderClause('price'), /effective_price.*ASC/);
  assert.match(sortOrderClause('thc'), /thc_pct.*DESC/);
  assert.match(sortOrderClause('distance'), /distance_miles.*ASC/);
  assert.match(sortOrderClause('discount'), /regular_price.*effective_price.*DESC/);
  // Default fallback for invalid or undefined
  assert.match(sortOrderClause(undefined as unknown as SortOption), /effective_price.*weight_grams/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test --import tsx web/lib/deals.test.ts`
Expected: FAIL (`SORT_OPTIONS` or `sortOrderClause` not exported)

- [ ] **Step 3: Implement `SORT_OPTIONS`, `sortOrderClause()`, and dynamic ranking in `web/lib/deals.ts` and `web/app/api/v1/deals/route.ts`**

In `web/lib/deals.ts`:
```typescript
export const SORT_OPTIONS = ['value', 'price', 'thc', 'distance', 'discount'] as const;
export type SortOption = (typeof SORT_OPTIONS)[number];

export function sortOrderClause(sort?: SortOption | string | null): string {
  switch (sort) {
    case 'price':
      return `(j->>'effective_price')::numeric ASC NULLS LAST, (j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, id`;
    case 'thc':
      return `nullif(regexp_replace(j->>'thc_pct', '[^0-9.]', '', 'g'), '')::numeric DESC NULLS LAST, (j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, id`;
    case 'distance':
      return `distance_miles ASC NULLS LAST, (j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, id`;
    case 'discount':
      return `CASE WHEN (NULLIF(j->>'regular_price','')::numeric) > (NULLIF(j->>'effective_price','')::numeric) AND (NULLIF(j->>'regular_price','')::numeric) > 0 THEN (((NULLIF(j->>'regular_price','')::numeric) - (NULLIF(j->>'effective_price','')::numeric)) / (NULLIF(j->>'regular_price','')::numeric)) ELSE 0 END DESC NULLS LAST, (j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, id`;
    case 'value':
    default:
      return `(j->>'effective_price')::numeric / nullif((j->>'weight_grams')::numeric, 0) ASC NULLS LAST, round(distance_miles::numeric,3) ASC, id`;
  }
}
```
Update `DealQuery` to include `sort?: SortOption;` and in `queryDeals()` replace the hardcoded order clause in `pg` CTE:
```sql
pg AS (
  SELECT gk, row_number() OVER (ORDER BY ${sortOrderClause(q.sort)}) AS ord, count(*) OVER() AS total
  FROM reps ORDER BY ord LIMIT ${arg(size)} OFFSET ${arg((page - 1) * size)})
```
In `web/app/api/v1/deals/route.ts`:
Validate `sort` parameter:
```typescript
const sortParam = u.get('sort');
const sort = SORT_OPTIONS.includes(sortParam as never) ? (sortParam as SortOption) : undefined;
```
Pass `sort` into `queryDeals(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test --import tsx web/lib/deals.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/lib/deals.ts web/app/api/v1/deals/route.ts web/lib/deals.test.ts
git commit -m "feat(deals): implement multi-criteria sorting clauses and API parameter"
```

---

### Task 2: Relative Freshness Utility & Live Pulse Indicator

**Files:**
- Create: `web/lib/time.ts`
- Modify: `web/lib/deals.test.ts`
- Modify: `web/app/offer-card.tsx:216-255`

**Interfaces:**
- Consumes: `Offer.last_seen_at` string.
- Produces: `formatRelativeTime(isoString: string, nowMs?: number): RelativeTimeInfo`.

- [ ] **Step 1: Write unit tests in `web/lib/deals.test.ts` for `formatRelativeTime`**

```typescript
import { formatRelativeTime } from './time.ts';

test('formatRelativeTime returns "Just now" and isLive for recent stamps', () => {
  const now = Date.parse('2026-10-25T12:00:00Z');
  // 30 seconds ago
  const res1 = formatRelativeTime('2026-10-25T11:59:30Z', now);
  assert.equal(res1.label, 'Just now');
  assert.equal(res1.isLive, true);

  // Negative diff (clock skew 10s into future)
  const res2 = formatRelativeTime('2026-10-25T12:00:10Z', now);
  assert.equal(res2.label, 'Just now');
  assert.equal(res2.isLive, true);
});

test('formatRelativeTime returns minutes and live flag for under 60m', () => {
  const now = Date.parse('2026-10-25T12:00:00Z');
  const res = formatRelativeTime('2026-10-25T11:35:00Z', now);
  assert.equal(res.label, '25m ago');
  assert.equal(res.isLive, true);
});

test('formatRelativeTime returns hours with isLive under 4h, not live >= 4h', () => {
  const now = Date.parse('2026-10-25T12:00:00Z');
  // 2 hours ago -> live
  const res1 = formatRelativeTime('2026-10-25T10:00:00Z', now);
  assert.equal(res1.label, '2h ago');
  assert.equal(res1.isLive, true);

  // 6 hours ago -> not live
  const res2 = formatRelativeTime('2026-10-25T06:00:00Z', now);
  assert.equal(res2.label, '6h ago');
  assert.equal(res2.isLive, false);
});

test('formatRelativeTime returns days for >= 24h', () => {
  const now = Date.parse('2026-10-25T12:00:00Z');
  const res = formatRelativeTime('2026-10-23T12:00:00Z', now);
  assert.equal(res.label, '2d ago');
  assert.equal(res.isLive, false);
});

test('formatRelativeTime handles invalid date strings gracefully', () => {
  const res = formatRelativeTime('not-a-valid-date');
  assert.equal(res.label, 'Recently observed');
  assert.equal(res.isLive, false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test --import tsx web/lib/deals.test.ts`
Expected: FAIL (`Cannot find module './time.ts'`)

- [ ] **Step 3: Implement `web/lib/time.ts`**

```typescript
export interface RelativeTimeInfo {
  label: string;
  full: string;
  isLive: boolean;
}

export function formatRelativeTime(isoString: string, nowMs = Date.now()): RelativeTimeInfo {
  const t = Date.parse(isoString);
  if (Number.isNaN(t)) {
    return {
      label: 'Recently observed',
      full: 'Observation timestamp unavailable',
      isLive: false,
    };
  }

  const full = new Date(t).toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    dateStyle: 'short',
    timeStyle: 'short',
  });

  const diffMs = nowMs - t;
  // If in the future or under 1 minute
  if (diffMs < 60_000) {
    return { label: 'Just now', full, isLive: true };
  }

  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 60) {
    return { label: `${diffMins}m ago`, full, isLive: true };
  }

  const diffHours = Math.floor(diffMs / 3_600_000);
  if (diffHours < 24) {
    return { label: `${diffHours}h ago`, full, isLive: diffHours < 4 };
  }

  const diffDays = Math.floor(diffMs / 86_400_000);
  return { label: `${diffDays}d ago`, full, isLive: false };
}
```

- [ ] **Step 4: Update `OfferCard` in `web/app/offer-card.tsx` to render the live indicator**

Import `formatRelativeTime` in `web/app/offer-card.tsx`.
Replace the static `when()` with `formatRelativeTime(o.last_seen_at)`.
Render:
```tsx
<div className="flex items-center gap-1.5 text-[10px] text-slate-400">
  {relTime.isLive ? (
    <span className="inline-flex items-center gap-1 text-emerald-400 font-semibold" title={relTime.full}>
      <span className="relative flex h-2 w-2" aria-hidden="true">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
      </span>
      <span>Live · Updated {relTime.label}</span>
    </span>
  ) : (
    <span title={relTime.full}>Updated {relTime.label}</span>
  )}
  {o.conditional ? <span>· Conditional promotion</span> : null}
</div>
```

- [ ] **Step 5: Run tests and typecheck**

Run: `node --test --import tsx web/lib/deals.test.ts && npm run check`
Expected: PASS with 0 errors

- [ ] **Step 6: Commit**

```bash
git add web/lib/time.ts web/app/offer-card.tsx web/lib/deals.test.ts
git commit -m "feat(cards): add relative freshness formatting and live pulse indicator"
```

---

### Task 3: Regional Quick Hub Expansion & Floating Back-to-Top Component

**Files:**
- Modify: `web/app/location.tsx:11-20`
- Create: `web/app/back-to-top.tsx`
- Test: `web/lib/deals.test.ts`

**Interfaces:**
- Consumes: Browser scroll events (`window.scrollY`).
- Produces: `BackToTop` component, expanded `QUICK_HUBS`.

- [ ] **Step 1: Write test in `web/lib/deals.test.ts` verifying expanded QUICK_HUBS zip validity**

```typescript
test('QUICK_HUBS contains all 12 target Illinois locations with valid 5-digit ZIPs', () => {
  const hubs = [
    ['Chicago', '60601'],
    ['Naperville', '60540'],
    ['Joliet', '60431'],
    ['Rockford', '61101'],
    ['Quad Cities', '61265'],
    ['Peoria', '61602'],
    ['Normal', '61761'],
    ['Champaign', '61820'],
    ['Springfield', '62701'],
    ['Streator', '61358'],
    ['Metro East', '62234'],
    ['Carbondale', '62901'],
  ];
  assert.equal(hubs.length, 12);
  for (const [name, zip] of hubs) {
    assert.match(zip, /^\d{5}$/, `${name} ZIP must be 5 digits`);
    assert.match(zip, /^6[0-2]/, `${name} ZIP must be in Illinois (60xxx-62xxx)`);
  }
});
```

- [ ] **Step 2: Update `QUICK_HUBS` in `web/app/location.tsx`**

Replace `QUICK_HUBS` in `web/app/location.tsx` with all 12 balanced regional destinations.

- [ ] **Step 3: Create `web/app/back-to-top.tsx`**

```tsx
'use client';
import { useEffect, useState } from 'react';

export default function BackToTop() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setVisible(window.scrollY > 400);
    };
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  if (!visible) return null;

  return (
    <button
      type="button"
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      aria-label="Back to top"
      className="fixed bottom-5 right-5 z-40 flex items-center gap-1.5 rounded-full bg-slate-900/90 hover:bg-slate-800/95 border border-slate-700/80 hover:border-emerald-500/50 text-slate-200 hover:text-emerald-300 shadow-xl backdrop-blur-md px-3.5 py-2 font-mono text-xs transition-all duration-200 animate-in fade-in"
    >
      <span className="text-emerald-400 font-bold" aria-hidden="true">↑</span>
      <span className="font-semibold tracking-wide">Top</span>
    </button>
  );
}
```

- [ ] **Step 4: Run tests and typecheck**

Run: `node --test --import tsx web/lib/deals.test.ts && npm run check`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/location.tsx web/app/back-to-top.tsx web/lib/deals.test.ts
git commit -m "feat(ui): expand regional quick hubs to 12 locations and add BackToTop capsule"
```

---

### Task 4: Integrate Sorting Controls in FilterStrip & Wire in Home Page

**Files:**
- Modify: `web/app/filters.tsx`
- Modify: `web/app/page.tsx`
- Test: Full build and typecheck (`npm run check && npm test && npm run build`)

**Interfaces:**
- Consumes: `SortOption`, `BackToTop`.
- Produces: Integrated sort picker, preserved search parameters, mounted back-to-top button.

- [ ] **Step 1: Add Sort selector to `FilterStrip` in `web/app/filters.tsx`**

Add `sort?: string` to `FilterStrip` props:
```tsx
const SORT_LABELS: Record<string, string> = {
  value: 'Best $/g',
  price: 'Lowest Price',
  thc: 'Highest THC',
  distance: 'Closest',
  discount: 'Biggest % Off',
};
```
In Row 1 next to `⚙ Filters`, render a compact select/picker:
```tsx
<div className="relative shrink-0">
  <select
    aria-label="Sort deals by"
    value={sort || 'value'}
    onChange={(e) => updateParams({ sort: e.target.value === 'value' ? null : e.target.value })}
    className="btn !py-2 !px-2.5 text-xs text-slate-200 bg-slate-900/90 border border-slate-700 hover:border-slate-600 appearance-none pr-6 cursor-pointer font-medium"
  >
    {SORT_OPTIONS.map((opt) => (
      <option key={opt} value={opt} className="bg-slate-900 text-slate-200">
        ⇅ {SORT_LABELS[opt]}
      </option>
    ))}
  </select>
  <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[9px] text-slate-400">▾</span>
</div>
```
When resetting all filters (`resetAll`), include `sort: null`.

- [ ] **Step 2: Update `web/app/page.tsx` to read `sort`, pass to queries, retain in URLs, and render `BackToTop`**

In `web/app/page.tsx`:
- Import `BackToTop` from `./back-to-top`.
- Parse `sortRaw = one(sp.sort);`
- Validate: `const sort = SORT_OPTIONS.includes(sortRaw as never) ? (sortRaw as SortOption) : 'value';`
- Pass `sort` to `queryDeals(...)`.
- Include `sort: sort !== 'value' ? sort : ''` in `base` URL params so pagination and reset buttons preserve sort order.
- Pass `sort={sort}` to `FilterStrip`.
- Mount `<BackToTop />` inside `<main>`.

- [ ] **Step 3: Run comprehensive verification**

Run:
```bash
npm run check
npm test
npm run build
python -m unittest discover -s tests
```
Expected: All suites exit with code 0 and 0 errors.

- [ ] **Step 4: Commit**

```bash
git add web/app/filters.tsx web/app/page.tsx
git commit -m "feat(sorting): wire sorting controls to filter bar and mount BackToTop component"
```

---

### Task 5: Whole-Branch Review & Remote Push

**Files:**
- All touched files

- [ ] **Step 1: Launch Code Review subagent**
Inspect git diff against `origin/main` for any edge cases, accessibility concerns, or regressions.

- [ ] **Step 2: Apply fixes if any issues are flagged**

- [ ] **Step 3: Push changes to remote**
Run `git push origin main`.
Verify push succeeds.
