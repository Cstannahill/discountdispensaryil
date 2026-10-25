# Shopper Utility, Saved Deals & Conversion Polish Design Specification

**Date:** 2026-10-25  
**Topic:** Frontend UI Third-Pass: Deal Card Conversion Utility, Saved Deals Shortlist, Smart Empty-State Recovery, and Illinois Tax Polish  
**Status:** Approved  

---

## 1. Context & Motivation

TerpScout's mobile-first web app (`web/`) enables cannabis deal discovery across Illinois. Following the sticky command bar consolidation and single-rail filter updates, a third-pass audit of the user purchasing journey identified three high-leverage opportunities:
1. **Shopper Validation & Psychological Conversion:** When deals are discounted, cards currently display plain strikethrough prices without highlighting the percentage or dollar savings. Dispensary addresses are plain text rather than 1-tap navigation routes, and sharing deals with friends requires manual link copying.
2. **Comparison Friction (Shortlist / Saved Deals):** Deal shoppers frequently browse 5–10 candidate offers across multiple categories and dispensaries before driving to a store. Without a shortlist, switching between categories or search filters loses their candidates.
3. **Empty-State Dead Ends:** When an overly restrictive filter combination yields 0 offers (e.g. Sativa + 14g in a 10-mile radius), the user faces plain text instead of actionable recovery actions.
4. **Illinois Tax Transparency:** Cannabis shoppers in Illinois face varying tax tiers depending on product type and potency (410 ILCS 705/65-10). The calculator needs clear, statutory tax tier breakdowns and mobile drag-handle polish.

---

## 2. Goals & Non-Goals

### Goals
- **Deal Card Conversion Utility (`OfferCard`):**
  - Compute and display high-contrast savings badges: `SAVE $X` and `Y% OFF` when regular price exceeds effective price.
  - Make dispensary store names 1-tap direct links to Google Maps search/directions.
  - Provide a 1-tap mobile Web Share button (`navigator.share`) with a clipboard copy fallback and floating toast feedback (`"Deal copied to clipboard!"`).
- **Saved / Bookmarked Deals Shortlist:**
  - 1-tap `🔖 Pin` button on every deal card, persisting pinned deals in `localStorage['terpscout.saved']`.
  - A `⭐ Saved (${count})` launcher button in the sticky command header (`LocationControl`).
  - A sleek `SavedModal` sheet allowing shoppers to view their pinned deals side-by-side across all categories, with 1-tap OTD calculation, menu links, and removal controls.
- **Actionable 0-Result Recovery (`page.tsx`):**
  - Replace static empty-state copy with 1-tap action buttons: `[✕ Clear All Filters]`, `[Show All Sizes]`, `[Show All Strains]`, and `[Expand Radius to 50 mi]`.
- **Illinois Tax Detail Footnote & Calculator Polish (`calculator.tsx`):**
  - Add native mobile drag-handle pill and a "Reset to Defaults" button.
  - Display exact statutory breakdown under 410 ILCS 705/65-10: 1% Med, 10% excise (≤35% THC Flower), 20% excise (Infused), and 25% excise (>35% THC / Concentrates) plus state/local retail taxes (~12%).

### Non-Goals
- Altering the backend database schema or crawler pipeline.
- Requiring user authentication or remote cloud account sync for saved deals (kept zero-friction via local storage).

---

## 3. Architecture & Component Design

### 3.1. Savings Math & Unit Tests (`web/lib/calculator.ts` & `web/lib/deals.test.ts`)
- Add helper function:
  ```ts
  export function calculateSavings(regularPrice?: number | string | null, effectivePrice?: number | string | null): {
    hasDiscount: boolean;
    savingsDollars: number;
    savingsPct: number;
  }
  ```
- Covered by unit tests in `web/lib/deals.test.ts` verifying rounding, zero/invalid prices, and formatting.

### 3.2. Deal Card Utility & Actions (`web/app/offer-card.tsx`)
- **Savings Callout:** In the Hero Price Box, if `hasDiscount` is true, render a prominent badge:
  `<span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-400/50 font-extrabold">{savingsPct}% OFF · SAVE ${savingsDollars.toFixed(0)}</span>`.
- **Google Maps Link:** Store name is wrapped with:
  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${o.store_name} dispensary Illinois`)}`.
- **Share Action:** 1-tap share button triggering `navigator.share` or fallback clipboard write, dispatching a lightweight toast event (`terpscout:toast`).
- **Bookmark Button:** Renders a 1-tap bookmark button (`🔖`) in the top right that toggles saved status in `localStorage['terpscout.saved']` and fires `terpscout:saved-change`.

### 3.3. Saved Deals Modal (`web/app/saved-modal.tsx`)
- A bottom sheet on mobile, centered modal on desktop (matching `CalculatorModal`).
- Listens for `terpscout:open-saved` and `terpscout:saved-change`.
- Renders pinned deals in a clean, scrollable list with:
  - Brand, product title, and category tag.
  - Price, $/g hero badge, and distance.
  - 1-tap `View on dispensary menu ↗`, `🧮 OTD`, and `Remove` button.
  - "Clear All" action at the top.
- Empty state: "No deals pinned yet. Tap the 🔖 button on any deal card to save it here for easy comparison."

### 3.4. Sticky Header Integration (`web/app/location.tsx`)
- Adds a `⭐ Saved (${count})` pill button next to `🧮 OTD Calc` in Row 1.
- Listens to `terpscout:saved-change` to update the badge counter in real-time.
- Tapping opens the `SavedModal`.

### 3.5. Smart Empty-State Recovery (`web/app/page.tsx`)
- If `r.items.length === 0`:
  Render quick recovery buttons based on active parameters:
  - `Reset all filters` (clears all filters and query).
  - `Switch to Any Size` (if `size !== 'any'`).
  - `Show All Strains` (if `strain !== ''`).
  - `Expand Radius to 50 mi` (if `radius < 50`).

### 3.6. Toast Notifications (`web/app/toast.tsx`)
- Lightweight client component mounted in `page.tsx` or root layout.
- Listens for `terpscout:toast` (`detail: string`) and displays a sleek bottom-floating notification that auto-dismisses after 2.5 seconds.

### 3.7. Calculator Modal Polish (`web/app/calculator.tsx`)
- Drag handle: `<div className="w-10 h-1 bg-slate-700/80 rounded-full mx-auto sm:hidden mb-2" aria-hidden="true" />`.
- "Reset to Defaults" button: restores $30 / 3.5g / 0% / 22%.
- Statutory Illinois Tax Footnote citing 410 ILCS 705/65-10.

---

## 4. Verification Plan

1. **Unit Tests:** `cd web && npm test` — verifies `calculateSavings`, existing tax inference, and filter utilities.
2. **Type Check:** `cd web && npm run typecheck` — 0 TypeScript errors.
3. **Production Build:** `cd web && npm run build` — Next.js build passes with exit code 0.
4. **Backend API Suite:** `.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v` — 19/19 OK.
