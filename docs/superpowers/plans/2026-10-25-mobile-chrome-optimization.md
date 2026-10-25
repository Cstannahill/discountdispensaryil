# Mobile Space & Chrome Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate TerpScout's mobile sticky chrome into a single ~72px command bar, eliminate the brittle secondary sticky category bar, condense the filter strip into a single horizontal scrolling rail with 1-tap mobile reset, and clean up non-standard styling tokens.

**Architecture:** Integrate the mobile category selector segments directly into the primary sticky header container (`web/app/location.tsx`) while coordinating category visibility on `CategoryGrid` (`web/app/categories.tsx`) via `localStorage` and a lightweight DOM event (`terpscout:category-change`). In `FilterStrip` (`web/app/filters.tsx`), merge Strain Type and Package Size pill tracks into a single horizontal scroll line, and make the `Reset` action directly accessible on mobile screens.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, Node.js test runner (`node --test`).

**Spec:** `docs/superpowers/specs/2026-10-25-mobile-chrome-optimization-design.md`

## Global Constraints

- Mobile sticky header height must not exceed ~75px.
- The desktop (`lg:`) 3-column layout and experience must remain identical.
- Category default on mobile must safely be `'flower'` with SSR hydration safety (guarded `localStorage` access).
- No external libraries or complex scroll-direction event listeners.
- All existing unit tests (8/8 in `web/lib/deals.test.ts`) and backend API tests (19/19 in `tests/test_api.py`) must pass.

## Review Focus

1. **Hydration mismatch on mobile category:** If `localStorage` is read during initial render, SSR HTML may diverge from client HTML. Verify `active` state initializes to `'flower'` and synchronizes inside `useEffect`.
2. **Narrow screen overflow (<360px):** If place name or brand title is too long, the header row could wrap into three lines. Verify `truncate` and `shrink-0` bounds prevent breaking.
3. **Single-rail filter scroll physics:** If strain and package size pills share one track without `.no-scrollbar` or flex shrinking, pills may clip or wrap. Verify single-rail horizontal overflow with `.shrink-0` on pills.
4. **Mobile filter reset responsiveness:** Tapping `✕ Reset` on mobile must clear search input state, delete all query parameters, and trigger router transition without requiring drawer open.
5. **Desktop category tab invisibility:** The mobile category segments in the header must remain completely hidden on desktop viewports (`lg:hidden`).

---

### Task 1: Condense `FilterStrip` Single-Rail Horizontal Track, Mobile Reset Affordance & Token Cleanup

**Files:**
- Modify: `web/app/filters.tsx`
- Test: `web/lib/deals.test.ts` (existing)

**Interfaces:**
- Consumes: `FilterStrip` props (`q`, `grade`, `strain`, `size`, `bogo`, `stale`, `unverified`).
- Produces: Updated `FilterStrip` component with single-rail horizontal pill track, mobile-accessible `✕ Reset` button, and standard Tailwind `py-0.5` tokens.

- [ ] **Step 1: Update `web/app/filters.tsx` with single-rail layout and mobile reset button**

In `web/app/filters.tsx`:
- Change Row 1 `Reset` button from `hidden sm:inline-flex` to `inline-flex` (with `hasAnyFilter` check) so mobile shoppers can reset all filters with one tap.
- Combine the Strain Type pill rail and Package Size pill rail into a single continuous horizontal scrolling track:
  ```tsx
  {/* Row 2: Unified Single-Rail Strain Type & Package Size Horizontal Track */}
  <div
    className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5"
    role="group"
    aria-label="Filter by strain type and package size"
  >
    {/* Strain Type Pills */}
    <button
      type="button"
      aria-pressed={!strain}
      onClick={() => updateParams({ strain: null })}
      className={`pill !py-1 !px-2.5 !text-[11px] shrink-0 ${!strain ? 'pill-active' : ''}`}
    >
      All Strains
    </button>
    {STRAINS.map((s) => {
      const active = strain.toLowerCase() === s.toLowerCase();
      return (
        <button
          key={s}
          type="button"
          aria-pressed={active}
          onClick={() => updateParams({ strain: active ? null : s })}
          className={`pill !py-1 !px-2.5 !text-[11px] shrink-0 ${active ? STRAIN_STYLES[s] + ' font-bold' : ''}`}
        >
          {s}
        </button>
      );
    })}

    <span className="text-slate-700 px-1 select-none shrink-0" aria-hidden="true">|</span>

    {/* Package Size Pills */}
    {SIZE_OPTIONS.map((opt) => {
      const active = (size || 'any') === opt.value;
      return (
        <button
          key={opt.value}
          type="button"
          aria-pressed={active}
          onClick={() => updateParams({ size: opt.value === 'any' ? null : opt.value })}
          className={`pill !py-1 !px-2.5 !text-[11px] font-mono shrink-0 ${active ? 'pill-active' : ''}`}
        >
          {opt.label}
        </button>
      );
    })}
  </div>
  ```
- Replace `py-0.2` on the count badge with `py-0.5`.

- [ ] **Step 2: Run typecheck and test**

Run: `cd web && npm run typecheck && npm test`
Expected: 0 TypeScript errors, 8/8 tests pass.

- [ ] **Step 3: Commit Task 1**

```bash
git add web/app/filters.tsx
git commit -m "feat(web): condense filter strip to single horizontal rail and enable mobile reset"
```

---

### Task 2: Synchronize `CategoryGrid` with Custom DOM Event & Strip Redundant Sticky `<nav>`

**Files:**
- Modify: `web/app/categories.tsx`

**Interfaces:**
- Consumes: DOM event `terpscout:category-change` (`detail: string`) and `localStorage['terpscout.category']`.
- Produces: Streamlined `CategoryGrid` component that synchronizes active column state without rendering its own redundant mobile sticky `<nav>`.

- [ ] **Step 1: Update `web/app/categories.tsx`**

In `web/app/categories.tsx`:
- Listen for `terpscout:category-change` custom event on `window`.
- Read initial active from `localStorage['terpscout.category']` in `useEffect` (fallback `'flower'`).
- Remove the `<nav className="lg:hidden sticky top-[53px] ...">` block.
- Keep the `<div className="cat-grid grid gap-4 lg:grid-cols-3 items-start" data-active={active}>` container and its children intact.
- Export helper or constant if needed for event name `terpscout:category-change`.

- [ ] **Step 2: Run typecheck and build check**

Run: `cd web && npm run typecheck && npm test`
Expected: 0 TypeScript errors, 8/8 tests pass.

- [ ] **Step 3: Commit Task 2**

```bash
git add web/app/categories.tsx
git commit -m "feat(web): strip redundant sticky category nav in favor of header integration"
```

---

### Task 3: Unify Sticky Command Header with Integrated Mobile Category Rail & Page Integration

**Files:**
- Modify: `web/app/location.tsx`
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: Category summary chips `chips: { id: string; label: string; total: number; color: string }[]` passed from `page.tsx` into `LocationControl`.
- Produces: Single unified sticky header (`sticky top-0 z-40`) rendering Row 1 (Location + License + Calc) and Row 2 (Mobile-only category segment), dispatching `terpscout:category-change` and persisting selection.

- [ ] **Step 1: Update `web/app/location.tsx` with mobile category segments**

In `web/app/location.tsx`:
- Accept `chips?: readonly { id: string; label: string; total: number; color: string }[]` prop.
- Maintain `activeCategory` state (default `'flower'`, synced from `localStorage['terpscout.category']`).
- Add helper to switch category:
  ```tsx
  const pickCategory = (id: string) => {
    setActiveCategory(id);
    try { localStorage.setItem('terpscout.category', id); } catch {}
    window.dispatchEvent(new CustomEvent('terpscout:category-change', { detail: id }));
  };
  ```
- In the return JSX, render Row 1 as a streamlined command bar with smooth truncation (`truncate max-w-[130px] sm:max-w-none` on place).
- In Row 2 (with `lg:hidden`), render the category segments:
  ```tsx
  {chips && chips.length > 0 && (
    <nav
      aria-label="Category navigation"
      className="lg:hidden flex items-center gap-1.5 overflow-x-auto no-scrollbar pt-2 border-t border-slate-800/80"
    >
      {orderedChips.map((c) => {
        const isSelected = activeCategory === c.id;
        return (
          <button
            key={c.id}
            type="button"
            aria-pressed={isSelected}
            onClick={() => pickCategory(c.id)}
            style={isSelected ? { borderColor: c.color } : undefined}
            className={`btn shrink-0 capitalize !py-1 !px-2.5 rounded-xl text-xs transition-all ${
              isSelected ? 'selected' : 'text-slate-300'
            }`}
          >
            <span aria-hidden="true">{ICONS[c.id] ?? '🌿'}</span>
            <span>{c.label}</span>
            {c.total >= 0 && (
              <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded-md ${
                isSelected ? 'bg-slate-950/30 text-slate-950 font-extrabold' : 'bg-slate-950/70 text-slate-400'
              }`}>
                {c.total}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  )}
  ```

- [ ] **Step 2: Update `web/app/page.tsx` to pass chips to `LocationControl`**

In `web/app/page.tsx`:
- Pass `chips={cats.map((c, i) => ({ id: c, label: c, total: results[i].total, color: ACCENT[c] }))}` into `<LocationControl />`.

- [ ] **Step 3: Run comprehensive verification**

Run:
1. `cd web && npm test`
2. `cd web && npm run typecheck`
3. `cd web && npm run build`
4. `.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v`

Expected: All suites PASS with 0 errors.

- [ ] **Step 4: Commit Task 3**

```bash
git add web/app/location.tsx web/app/page.tsx
git commit -m "feat(web): integrate mobile category tabs into unified sticky header"
```
