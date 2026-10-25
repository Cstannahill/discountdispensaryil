# Shopper Utility, Saved Deals & Conversion Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement shopper conversion features including savings % & dollar badges, 1-tap Google Maps dispensary navigation, 1-tap mobile deal sharing with floating toast feedback, a local-storage Saved Deals shortlist modal, smart 0-result recovery buttons, and Illinois statutory tax transparency (410 ILCS 705/65-10).

**Architecture:** Add `calculateSavings` to `web/lib/calculator.ts` with unit tests in `web/lib/deals.test.ts`. Create `web/app/toast.tsx` for clipboard/share feedback and `web/app/saved-modal.tsx` for cross-category shortlist comparison. Enhance `OfferCard` (`web/app/offer-card.tsx`) with savings badges, Google Maps links, native Web Share, and pin toggle. Integrate the saved deals trigger in `LocationControl` (`web/app/location.tsx`), 1-tap recovery buttons in `web/app/page.tsx`, and statutory footnotes + drag handle in `web/app/calculator.tsx`.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, Web Share API, LocalStorage, Node.js test runner (`node --test`).

**Spec:** `docs/superpowers/specs/2026-10-25-shopper-utility-saved-deals-design.md`

## Global Constraints

- Saved deals must be persisted in `localStorage['terpscout.saved']` with zero-friction local client storage (no account required).
- All `localStorage` accesses must occur inside `useEffect` or client event callbacks to prevent SSR hydration mismatches.
- Web Share must gracefully fall back to clipboard writing (`navigator.clipboard.writeText`) on desktop and unsupported browsers.
- Google Maps search queries must properly escape dispensary names and target `_blank` with `rel="noopener noreferrer"`.
- All existing unit tests (8/8) plus new savings tests and backend API tests (19/19) must pass cleanly.

## Review Focus

1. **Savings calculation edge cases:** If regular price $\le$ effective price, or either is null/empty/NaN, `hasDiscount` must be false with 0% savings.
2. **Web Share API security context & permission rejection:** If a user cancels the native share sheet (`AbortError`), it must not crash or trigger the clipboard fallback erroneously.
3. **Saved deals state synchronization:** When a deal is pinned/unpinned on an `OfferCard` or inside `SavedModal`, all card pin states and header badge counters must synchronize across the page via `terpscout:saved-change`.
4. **Google Maps URL encoding:** Dispensary names containing ampersands, slashes, or city identifiers (e.g. `Rise - Mundelein & Medical`) must encode safely without malforming the query parameter.
5. **Recovery action URL cleanliness:** Tapping recovery buttons in `page.tsx` must navigate to valid Next.js query parameter states without leaving stale or empty parameter keys.

---

### Task 1: Add Savings Calculation Logic & Unit Tests

**Files:**
- Modify: `web/lib/calculator.ts`
- Modify: `web/lib/deals.test.ts`

**Interfaces:**
- Consumes: `regularPrice?: number | string | null`, `effectivePrice?: number | string | null`.
- Produces: `calculateSavings(regular, effective): { hasDiscount: boolean; savingsDollars: number; savingsPct: number }`.

- [ ] **Step 1: Write failing unit tests for `calculateSavings`**

In `web/lib/deals.test.ts`:
```ts
describe('calculateSavings', () => {
  it('calculates savings percentage and dollar difference accurately', () => {
    const s1 = calculateSavings('50', '35');
    assert.equal(s1.hasDiscount, true);
    assert.equal(s1.savingsDollars, 15);
    assert.equal(s1.savingsPct, 30);

    const s2 = calculateSavings(60, 45);
    assert.equal(s2.hasDiscount, true);
    assert.equal(s2.savingsDollars, 15);
    assert.equal(s2.savingsPct, 25);
  });

  it('returns hasDiscount false when regular price is less than or equal to effective price or invalid', () => {
    assert.equal(calculateSavings('35', '35').hasDiscount, false);
    assert.equal(calculateSavings('30', '40').hasDiscount, false);
    assert.equal(calculateSavings(null, '30').hasDiscount, false);
    assert.equal(calculateSavings('50', null).hasDiscount, false);
    assert.equal(calculateSavings('0', '0').hasDiscount, false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL with "calculateSavings is not defined".

- [ ] **Step 3: Implement `calculateSavings` in `web/lib/calculator.ts`**

In `web/lib/calculator.ts`:
```ts
export function calculateSavings(
  regularPrice?: number | string | null,
  effectivePrice?: number | string | null
): {
  hasDiscount: boolean;
  savingsDollars: number;
  savingsPct: number;
} {
  const reg = Number(regularPrice);
  const eff = Number(effectivePrice);
  if (!Number.isFinite(reg) || !Number.isFinite(eff) || reg <= 0 || eff < 0 || reg <= eff) {
    return { hasDiscount: false, savingsDollars: 0, savingsPct: 0 };
  }
  const savingsDollars = reg - eff;
  const savingsPct = Math.round((savingsDollars / reg) * 100);
  return {
    hasDiscount: true,
    savingsDollars,
    savingsPct,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test && npm run typecheck`
Expected: PASS (suites 5, tests 10/10 pass, 0 typecheck errors).

- [ ] **Step 5: Commit Task 1**

```bash
git add web/lib/calculator.ts web/lib/deals.test.ts
git commit -m "feat(web): add calculateSavings helper and unit tests"
```

---

### Task 2: Build Floating Toast Notification & Saved Deals Modal Sheet

**Files:**
- Create: `web/app/toast.tsx`
- Create: `web/app/saved-modal.tsx`

**Interfaces:**
- Consumes: Custom DOM events `terpscout:toast` (`detail: string`), `terpscout:open-saved`, `terpscout:saved-change`, and `localStorage['terpscout.saved']`.
- Produces: `ToastContainer` and `SavedModal` components, and helpers `showToast(msg: string)` and `openSavedDeals()`.

- [ ] **Step 1: Create `web/app/toast.tsx`**

Create `web/app/toast.tsx` with `showToast(msg: string)` and client component `ToastContainer` that animates a sleek floating badge at bottom-center of the viewport.

- [ ] **Step 2: Create `web/app/saved-modal.tsx`**

Create `web/app/saved-modal.tsx` with:
- `openSavedDeals()` helper.
- `SavedDeal` type interface.
- Bottom sheet on mobile with drag handle, centered modal on desktop.
- List of saved deals with remove, direct dispensary link, 1-tap OTD calculator seed, and "Clear All".
- Empty state with clear instructions.

- [ ] **Step 3: Run typecheck**

Run: `cd web && npm run typecheck`
Expected: 0 errors.

- [ ] **Step 4: Commit Task 2**

```bash
git add web/app/toast.tsx web/app/saved-modal.tsx
git commit -m "feat(web): add toast notifications and saved deals modal sheet"
```

---

### Task 3: Upgrade `OfferCard` with Savings % Badges, 1-Tap Google Maps Directions, Web Share Button, and Pin Toggle

**Files:**
- Modify: `web/app/offer-card.tsx`

**Interfaces:**
- Consumes: `Offer` object, `calculateSavings` from `web/lib/calculator`, `showToast` from `web/app/toast`, `localStorage['terpscout.saved']`.
- Produces: Enhanced `OfferCard` with:
  - Savings callout (`SAVE $X · Y% OFF`).
  - Google Maps link on dispensary name.
  - Native Web Share button with clipboard fallback.
  - 1-tap `🔖` pin toggle.

- [ ] **Step 1: Update `web/app/offer-card.tsx`**

Implement:
- Savings badge inside Hero Price Box:
  ```tsx
  {savings.hasDiscount && (
    <span className="inline-block bg-emerald-500/20 text-emerald-300 border border-emerald-400/50 rounded-md px-1.5 py-0.5 text-[10px] font-mono font-bold mb-1">
      {savings.savingsPct}% OFF · SAVE ${savings.savingsDollars.toFixed(0)}
    </span>
  )}
  ```
- Store directions link targeting Google Maps search.
- Native `navigator.share` handler sharing title, price, $/g, dispensary, and link, falling back to clipboard write and `showToast("Deal copied to clipboard!")`.
- Pin bookmark button toggling `localStorage['terpscout.saved']` and dispatching `terpscout:saved-change`.

- [ ] **Step 2: Run typecheck and test**

Run: `cd web && npm run typecheck && npm test`
Expected: 0 errors, 10/10 tests pass.

- [ ] **Step 3: Commit Task 3**

```bash
git add web/app/offer-card.tsx
git commit -m "feat(web): add savings badges, maps directions, share button, and pin toggle to offer cards"
```

---

### Task 4: Add Saved Deals Trigger to Sticky Header, Implement Smart 0-Result Recovery, and Polish Calculator Modal

**Files:**
- Modify: `web/app/location.tsx`
- Modify: `web/app/page.tsx`
- Modify: `web/app/calculator.tsx`

**Interfaces:**
- Consumes: `SavedModal`, `ToastContainer`, `openSavedDeals()`, active query/filter parameters.
- Produces: Complete end-to-end third-pass shopper experience.

- [ ] **Step 1: Update `web/app/location.tsx`**

Add `⭐ Saved` button in Row 1:
- Listens to `terpscout:saved-change` and checks `localStorage['terpscout.saved']` count.
- Displays `⭐ (${savedCount})` when count > 0 (or `⭐ Saved`).
- Tapping opens `openSavedDeals()`.

- [ ] **Step 2: Update `web/app/page.tsx`**

Implement:
- Mount `<SavedModal />` and `<ToastContainer />`.
- When `r.items.length === 0`, render smart recovery card with:
  - `[✕ Clear All Filters]`
  - `[Show All Sizes]` (if `size !== 'any'`)
  - `[Show All Strains]` (if `strain !== ''`)
  - `[Expand Radius to 50 mi]` (if `radius < 50`)

- [ ] **Step 3: Polish `web/app/calculator.tsx`**

Implement:
- Native mobile drag-handle pill.
- "Reset to Defaults" button restoring $30 / 3.5g / 0% / 22%.
- Statutory Illinois Tax Footnote (410 ILCS 705/65-10): Med 1%, Rec Flower (≤35% THC) 10% excise + ~12% tax = ~22%, Rec Infused 20% excise + ~12% = ~32%, Rec Concentrates & >35% THC 25% excise + ~12% = ~37%.

- [ ] **Step 4: Run full verification**

Run:
1. `cd web && npm test`
2. `cd web && npm run typecheck`
3. `cd web && npm run build`
4. `.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v`

Expected: All suites PASS with 0 errors.

- [ ] **Step 5: Commit Task 4**

```bash
git add web/app/location.tsx web/app/page.tsx web/app/calculator.tsx
git commit -m "feat(web): add header saved trigger, smart empty-state recovery, and calculator tax polish"
```
