# TerpScout Mobile-First Web Redesign & Legacy Frontend Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the `web/` Next.js app into a modern, mobile-first botanical deals experience with instant strain/size/grade filtering and an Out-The-Door (OTD) tax calculator, while relocating Playwright to `web/` and retiring `frontend/`.

**Architecture:** We extend `web/lib/deals.ts` and `web/app/api/v1/deals/route.ts` with $\pm 3\%$ package-size bucket filtering (`size`) and bucket-consistent strain filtering (`strain_type`), plus pure helper functions for OTD tax calculation. We replace the static above-the-fold forms in `web/app/` with a compact sticky command header (`LocationControl` pill + `Rec`/`Med` toggle + `OTD` button), an instant client-driven filter strip (`FilterStrip`), a mobile-first category switcher defaulting to `flower` (`CategoryGrid`), a high-contrast botanical `OfferCard` with one-tap `OTD` pre-fill, and an Illinois-aware `CalculatorModal`. Finally, we move `playwright` into `web/package.json`, update `backend/browser_worker.cjs`, remove `frontend/`, and clean up `backend/main.py` and docs.

**Tech Stack:** Next.js 16 (App Router, Server + Client Components), React 19, TypeScript 7, Tailwind CSS 3.4, Neon Serverless Postgres (`@neondatabase/serverless`), Node.js native test runner (`node --experimental-strip-types --test`), Python 3.13 + `unittest` + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-25-frontend-redesign-design.md`

## Global Constraints

- Target branch: `main` (all commits land on `main`).
- Node 22.12+, Python 3.13+ (always use `.venv\Scripts\python.exe`).
- `index.html` and `terpscout.db.before-live.sqlite3` are preserved originals; never edit.
- All `<input>` and `<select>` controls on mobile must use `text-base sm:text-sm` (`16px` on mobile) to prevent iOS Safari auto-zoom on focus.
- Maintain `data-cat={category}` on category `<section>` elements and `.cat-grid[data-active=...]` CSS rules so mobile category filtering works with zero layout shift.

## Review Focus

- **Hybrid-leaning strain labels in SQL vs JS:** Dispensary menus label strains like `"Indica Dominant Hybrid"` or `"Sativa-Hybrid"`. Both `strainBucket()` in JS and `strainClause()` in Postgres SQL must classify `"Indica Dominant Hybrid"` as `Indica`, `"Sativa-Hybrid"` as `Sativa`, and `"Balanced Hybrid"` as `Hybrid` so UI strain pills and grouped card strain buckets never disagree.
- **Invalid or out-of-range `size` query parameters:** Passing `?size=abc`, `?size=-5`, `?size=0`, or `?size=any` must never produce invalid SQL or NaN parameters; only allowed positive numeric sizes (`0.5`, `1`, `3.5`, `7`, `14`, `28`) or valid positive numbers should add the $\pm 3\%$ weight predicate.
- **Category-scoped `size` filtering on the 3-column board:** Selecting a flower-specific weight like `3.5g` or `28g` on `page.tsx` must filter the `flower` query without wiping out `concentrate` and `vapes` columns (which are `0.5g` / `1g`), whereas selecting `0.5g` or `1g` applies across categories that carry those weights.
- **OTD Calculator edge inputs and tax preset inference:** Zero/negative weight, negative price, or discount `> 100%` must be rejected cleanly (`valid: false`) rather than rendering `NaN` or `$Infinity/g`; pre-filling from a deal card must pick `1%` for `medicinal`, `37%` for `concentrate` or `thc_pct > 35`, `32%` for `vapes` or `flower_grade === 'infused'`, and `22%` for standard recreational flower.
- **Playwright resolution after `frontend/` deletion:** `backend/browser_worker.cjs` must resolve `chromium` from `../web/node_modules/playwright` and pass real Chrome rendering tests after `frontend/` is deleted.

---

### Task 1: Relocate Playwright to `web/` and Retire `frontend/`

**Files:**
- Modify: `web/package.json`
- Modify: `backend/browser_worker.cjs:1-5`
- Modify: `docs/site-maps/raw/batch-5/tools/survey.cjs:1-5`
- Modify: `backend/main.py:357-383`
- Modify: `.gitignore`
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Delete: `frontend/` (entire directory)
- Test: `tests/test_api.py`, `tests/test_browser_render.py`

**Interfaces:**
- Consumes: `web/package.json` dependencies
- Produces: `web/node_modules/playwright` required by `backend/browser_worker.cjs`; `backend/main.py` without `frontend/dist` static mounts.

- [ ] **Step 1: Add `playwright` to `web/package.json` and install**

Update `web/package.json` `devDependencies` to include `"playwright": "1.64.0-alpha-1790635538000"` (the exact version cached and matching the local Chromium build):

```json
{
  "name": "terpscout-web",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev -H 127.0.0.1 -p 3000",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit",
    "test": "node --experimental-strip-types --test lib/*.test.ts"
  },
  "dependencies": {
    "@neondatabase/serverless": "^1.2.0",
    "next": "^16.4.2",
    "react": "^19.3.1",
    "react-dom": "^19.3.1"
  },
  "devDependencies": {
    "@types/node": "^26.6.5",
    "@types/react": "^19.3.0",
    "@types/react-dom": "^19.3.0",
    "autoprefixer": "^10.6.1",
    "playwright": "1.64.0-alpha-1790635538000",
    "postcss": "^8.5.31",
    "tailwindcss": "^3.4.19",
    "typescript": "^7.0.2"
  }
}
```

Run in `web/`:
```powershell
cd web; npm install
```

- [ ] **Step 2: Update `backend/browser_worker.cjs` and `docs/site-maps/raw/batch-5/tools/survey.cjs`**

In `backend/browser_worker.cjs`, replace line 3:
```javascript
/* Ordinary Chrome rendering through validated captured HTTP or a public-only
 * native tunnel. Shopping preferences are distinct from age confirmation. */
const { chromium } = require('../web/node_modules/playwright');
const readline = require('node:readline');
```

In `docs/site-maps/raw/batch-5/tools/survey.cjs`, replace line 2:
```javascript
const path=require('node:path');
const {chromium}=require(path.resolve(__dirname,'../../../../../web/node_modules/playwright'));
```

- [ ] **Step 3: Remove `frontend/dist` routes from `backend/main.py` and delete `frontend/`**

In `backend/main.py`, replace lines 357-380 with:
```python
    @app.get("/reference/legacy-demo", include_in_schema=False)
    def legacy_reference():
        text = (BASE_DIR / "index.html").read_text(encoding="utf-8")
        banner = '<aside style="position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#78350f;color:white;padding:12px;text-align:center">LEGACY VISUAL REFERENCE — simulated stores, products and sync events. Not live data.</aside>'
        return HTMLResponse(text.replace("</body>", banner + "</body>"))

    @app.get("/api/{path:path}", include_in_schema=False)
    def unknown_api(path: str):
        return JSONResponse(status_code=404, content={"detail": {"code": "unknown_api", "message": "Unknown API route"}})

    return app
```

Delete the `frontend/` directory:
```powershell
Remove-Item -Recurse -Force frontend
```

- [ ] **Step 4: Update `.gitignore`, `CLAUDE.md`, and `README.md`**

In `.gitignore`, replace `frontend/dist/`, `frontend/.playwright-cli/`, and `frontend/output/` with `web/.next/`:
```gitignore
# Dependencies and build output
node_modules/
web/.next/
__pycache__/
*.pyc
```

In `CLAUDE.md`, update lines 3, 9, and 12 to reference `web/` instead of `frontend/`:
```markdown
TerpScout: finds the best cannabis deals ($/g) near a location by ingesting full dispensary menus. FastAPI + SQLite + APScheduler backend, Next.js/React/TS frontend (`web/`), Node/Playwright (installed Chrome) browser fallback. Illinois registry is the only candidate source today. See `PROJECT_STATUS_REPORT.md` for current measured coverage (22 of 190 regional stores have an accepted menu) and `docs/` for history; do not trust older counts in other docs.
```
and in commands:
```powershell
cd web; npm run dev               # :3000, Next.js web app
```
and:
```powershell
cd web; npm run typecheck; npm test; npm run build
```

In `README.md`, update the setup and verification sections to reference `web/` (`Set-Location web`, `npm install`, `npm test`, `npm run build`).

- [ ] **Step 5: Verify backend tests and Playwright browser test pass**

Run:
```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:TERPSCOUT_BROWSER_TEST='1'; .venv\Scripts\python.exe -m unittest discover -s tests -p test_browser_render.py -k test_dom_observations_use_unambiguous_sale_price_and_fractional_mass -v
```
Expected: All unit tests and the real Chrome Playwright test pass using `web/node_modules/playwright`.

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "Retire legacy frontend/ and relocate Playwright to web/"
```

---

### Task 2: Query Filters (`size`, `strain_type`) & OTD Calculator Logic in `web/lib/`

**Files:**
- Modify: `web/lib/deals.ts`
- Modify: `web/app/api/v1/deals/route.ts`
- Create: `web/lib/calculator.ts`
- Create: `web/lib/deals.test.ts`
- Test: `web/lib/deals.test.ts`

**Interfaces:**
- Consumes: `web/lib/db.ts`, `web/lib/origin.ts`, `web/lib/product-links.ts`
- Produces:
  - `web/lib/deals.ts`:
    - `CATEGORIES = ['concentrate', 'flower', 'vapes'] as const`
    - `GRADES = ['whole', 'smalls', 'shake', 'infused', 'all'] as const`
    - `LICENSES = ['recreational', 'medicinal'] as const`
    - `STRAINS = ['Indica', 'Sativa', 'Hybrid'] as const`
    - `SIZES = ['any', '0.5', '1', '3.5', '7', '14', '28'] as const`
    - `FLOWER_ONLY_SIZES = new Set(['3.5', '7', '14', '28'])`
    - `sizeForCategory(category: string, size?: string): string | undefined`
    - `parseSize(v?: string | null): number | null`
    - `strainClause(strain: string, bind: (v: unknown) => string): string | null`
    - `DealQuery` with `size?: string` and `strain_type?: string`
  - `web/lib/calculator.ts`:
    - `TAX_PRESETS`: Illinois tax presets (`med`, `rec_flower`, `rec_vape`, `rec_high`)
    - `inferTaxRate(offer?: { license_type?: string; category?: string; flower_grade?: string | null; thc_pct?: string | null }): number`
    - `calculateOtd(input: { price: number; weight: number; discountPct: number; taxPct: number }): { valid: boolean; discountedSubtotal: number; preTaxPerGram: number; outTheDoorTotal: number; outTheDoorPerGram: number }`

- [ ] **Step 1: Write the failing unit tests in `web/lib/deals.test.ts`**

Create `web/lib/deals.test.ts`:
```typescript
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { strainBucket, parseSize, sizeForCategory, strainClause } from './deals.ts';
import { calculateOtd, inferTaxRate } from './calculator.ts';
import { parseOrigin } from './origin.ts';

describe('strainBucket and strainClause consistency', () => {
  it('buckets dominant-leaning and hybrid labels consistently', () => {
    assert.equal(strainBucket('Indica'), 'Indica');
    assert.equal(strainBucket('Indica Dominant Hybrid'), 'Indica');
    assert.equal(strainBucket('Sativa'), 'Sativa');
    assert.equal(strainBucket('Sativa-Hybrid'), 'Sativa');
    assert.equal(strainBucket('Hybrid'), 'Hybrid');
    assert.equal(strainBucket('Balanced Hybrid'), 'Hybrid');
    assert.equal(strainBucket(null), 'Unspecified');
    assert.equal(strainBucket(''), 'Unspecified');
  });

  it('builds SQL predicates that match strainBucket precedence', () => {
    const bound: unknown[] = [];
    const bind = (v: unknown) => (bound.push(v), `$${bound.length}`);
    const ind = strainClause('Indica', bind);
    assert.ok(ind?.includes("position('indica'"));
    const sat = strainClause('Sativa', bind);
    assert.ok(sat?.includes("position('sativa'") && sat?.includes("position('indica'"));
    const hyb = strainClause('Hybrid', bind);
    assert.ok(hyb?.includes("position('hybrid'") && hyb?.includes("position('indica'") && hyb?.includes("position('sativa'"));
    assert.equal(strainClause('all', bind), null);
    assert.equal(strainClause('', bind), null);
  });
});

describe('package size parsing and category scoping', () => {
  it('rejects invalid, negative, zero, or "any" sizes and accepts positive gram weights', () => {
    assert.equal(parseSize('any'), null);
    assert.equal(parseSize(''), null);
    assert.equal(parseSize(null), null);
    assert.equal(parseSize('abc'), null);
    assert.equal(parseSize('-3.5'), null);
    assert.equal(parseSize('0'), null);
    assert.equal(parseSize('3.5'), 3.5);
    assert.equal(parseSize('0.5'), 0.5);
    assert.equal(parseSize('28'), 28);
  });

  it('scopes flower-only weights (3.5g, 7g, 14g, 28g) to flower on multi-column views while keeping 0.5g/1g universal', () => {
    assert.equal(sizeForCategory('flower', '3.5'), '3.5');
    assert.equal(sizeForCategory('concentrate', '3.5'), undefined);
    assert.equal(sizeForCategory('vapes', '3.5'), undefined);
    assert.equal(sizeForCategory('concentrate', '1'), '1');
    assert.equal(sizeForCategory('vapes', '0.5'), '0.5');
    assert.equal(sizeForCategory('flower', 'any'), undefined);
  });
});

describe('OTD calculator and Illinois tax inference', () => {
  it('calculates discounted pre-tax $/g, OTD total, and OTD $/g accurately', () => {
    const res = calculateOtd({ price: 40, weight: 3.5, discountPct: 25, taxPct: 22 });
    assert.equal(res.valid, true);
    assert.equal(res.discountedSubtotal, 30);
    assert.ok(Math.abs(res.preTaxPerGram - 30 / 3.5) < 1e-6);
    assert.ok(Math.abs(res.outTheDoorTotal - 36.6) < 1e-6);
    assert.ok(Math.abs(res.outTheDoorPerGram - 36.6 / 3.5) < 1e-6);
  });

  it('marks invalid inputs as valid: false without NaN or Infinity', () => {
    assert.equal(calculateOtd({ price: -10, weight: 3.5, discountPct: 0, taxPct: 20 }).valid, false);
    assert.equal(calculateOtd({ price: 30, weight: 0, discountPct: 0, taxPct: 20 }).valid, false);
    assert.equal(calculateOtd({ price: 30, weight: 3.5, discountPct: 120, taxPct: 20 }).valid, false);
    assert.equal(calculateOtd({ price: 30, weight: 3.5, discountPct: 0, taxPct: -5 }).valid, false);
  });

  it('infers Illinois tax rate from license, category, flower grade, and THC %', () => {
    assert.equal(inferTaxRate({ license_type: 'medicinal', category: 'concentrate', thc_pct: '80' }), 1);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'concentrate', thc_pct: '72' }), 37);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', thc_pct: '38' }), 37);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'vapes', thc_pct: '85' }), 32);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', flower_grade: 'infused', thc_pct: '30' }), 32);
    assert.equal(inferTaxRate({ license_type: 'recreational', category: 'flower', flower_grade: 'whole', thc_pct: '24' }), 22);
  });
});

describe('parseOrigin', () => {
  it('parses valid coordinates and clamps radius to 200 miles', () => {
    const p = new Map([['lat', '40.6936'], ['lon', '-89.589'], ['radius', '500'], ['place', 'Peoria, IL']]);
    const o = parseOrigin((k) => p.get(k));
    assert.deepEqual(o, { latitude: 40.6936, longitude: -89.589, radius_miles: 200, label: 'Peoria, IL' });
  });
});
```

- [ ] **Step 2: Run `npm test` in `web/` to verify it fails**

Run:
```powershell
cd web; npm test
```
Expected: FAIL (`Cannot find module './calculator.ts'` / missing exports `parseSize`, `sizeForCategory`, `strainClause`).

- [ ] **Step 3: Implement `web/lib/calculator.ts` and update `web/lib/deals.ts` & `web/app/api/v1/deals/route.ts`**

Create `web/lib/calculator.ts`:
```typescript
export interface TaxPreset {
  id: string;
  label: string;
  shortLabel: string;
  rate: number;
  detail: string;
}

export const TAX_PRESETS: readonly TaxPreset[] = [
  { id: 'med', label: 'Medical (~1%)', shortLabel: 'Med 1%', rate: 1, detail: 'IL medical cannabis 1% state retail tax' },
  { id: 'rec_flower', label: 'Rec Flower ≤35% (~22%)', shortLabel: 'Flower 22%', rate: 22, detail: '10% IL excise + state/local retail taxes' },
  { id: 'rec_vape', label: 'Rec Vape / Infused (~32%)', shortLabel: 'Vape/Infused 32%', rate: 32, detail: '20% IL infused excise + state/local taxes' },
  { id: 'rec_high', label: 'Rec >35% THC / Conc (~37%)', shortLabel: 'Conc/>35% 37%', rate: 37, detail: '25% IL high-THC excise + state/local taxes' },
] as const;

export function inferTaxRate(offer?: {
  license_type?: string | null;
  category?: string | null;
  flower_grade?: string | null;
  thc_pct?: string | null;
}): number {
  if (!offer) return 22;
  if (offer.license_type === 'medicinal') return 1;
  const thc = Number(offer.thc_pct);
  if (offer.category === 'concentrate' || (Number.isFinite(thc) && thc > 35)) return 37;
  if (offer.category === 'vapes' || offer.flower_grade === 'infused') return 32;
  return 22;
}

export function calculateOtd(input: {
  price: number;
  weight: number;
  discountPct: number;
  taxPct: number;
}) {
  const { price, weight, discountPct, taxPct } = input;
  const valid =
    Number.isFinite(price) &&
    Number.isFinite(weight) &&
    Number.isFinite(discountPct) &&
    Number.isFinite(taxPct) &&
    price >= 0 &&
    weight > 0 &&
    discountPct >= 0 &&
    discountPct <= 100 &&
    taxPct >= 0 &&
    taxPct <= 100;
  if (!valid) {
    return {
      valid: false,
      discountedSubtotal: 0,
      preTaxPerGram: 0,
      outTheDoorTotal: 0,
      outTheDoorPerGram: 0,
    };
  }
  const discountedSubtotal = price * (1 - discountPct / 100);
  const outTheDoorTotal = discountedSubtotal * (1 + taxPct / 100);
  return {
    valid: true,
    discountedSubtotal,
    preTaxPerGram: discountedSubtotal / weight,
    outTheDoorTotal,
    outTheDoorPerGram: outTheDoorTotal / weight,
  };
}
```

Update `web/lib/deals.ts` to add `STRAINS`, `SIZES`, `FLOWER_ONLY_SIZES`, `parseSize`, `sizeForCategory`, `strainClause`, and wire `size` and `strainClause` into `queryDeals`:
```typescript
export const CATEGORIES = ['concentrate', 'flower', 'vapes'] as const;
export const GRADES = ['whole', 'smalls', 'shake', 'infused', 'all'] as const;
export const LICENSES = ['recreational', 'medicinal'] as const;
export const STRAINS = ['Indica', 'Sativa', 'Hybrid'] as const;
export const SIZES = ['any', '0.5', '1', '3.5', '7', '14', '28'] as const;
export const FLOWER_ONLY_SIZES = new Set(['3.5', '7', '14', '28']);

export function parseSize(v?: string | null): number | null {
  if (!v || v === 'any') return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 && n <= 200 ? n : null;
}

export function sizeForCategory(category: string, size?: string | null): string | undefined {
  const n = parseSize(size);
  if (n == null) return undefined;
  const key = String(size).trim();
  if (FLOWER_ONLY_SIZES.has(key) && category !== 'flower') return undefined;
  return key;
}

export function strainClause(strain?: string | null, _bind?: (v: unknown) => string): string | null {
  const s = (strain ?? '').trim().toLowerCase();
  const col = `lower(coalesce(j->>'strain_type',''))`;
  if (s === 'indica') return `position('indica' in ${col}) > 0`;
  if (s === 'sativa') return `(position('sativa' in ${col}) > 0 AND position('indica' in ${col}) = 0)`;
  if (s === 'hybrid') return `(position('hybrid' in ${col}) > 0 AND position('indica' in ${col}) = 0 AND position('sativa' in ${col}) = 0)`;
  return null;
}
```
And inside `queryDeals(q: DealQuery)` in `web/lib/deals.ts`:
- Add `size?: string;` to `DealQuery`.
- Replace `if (q.strain_type && q.strain_type.toLowerCase() !== 'all') where.push(...)` with:
  ```typescript
  const sClause = strainClause(q.strain_type, arg);
  if (sClause) where.push(sClause);
  const sz = parseSize(q.size);
  if (sz != null) {
    const ref = arg(sz);
    where.push(`abs((NULLIF(j->>'weight_grams','')::numeric) - ${ref}::numeric) <= (${ref}::numeric * 0.03)`);
  }
  ```

Update `web/app/api/v1/deals/route.ts` to pass `size: u.get('size') || undefined` to `queryDeals`.

- [ ] **Step 4: Run `npm test` and `npm run typecheck` in `web/`**

Run:
```powershell
cd web; npm test; npm run typecheck
```
Expected: All unit tests in `web/lib/deals.test.ts` PASS and `tsc --noEmit` exits 0.

- [ ] **Step 5: Commit**

```powershell
git add web/lib/deals.ts web/lib/calculator.ts web/lib/deals.test.ts web/app/api/v1/deals/route.ts
git commit -m "Add package size filter, bucket-consistent strain filter, and OTD calculator logic"
```

---

### Task 3: Botanical Theme, Typography & Global Styles (`web/app/layout.tsx`, `web/app/globals.css`, `web/tailwind.config.cjs`)

**Files:**
- Modify: `web/app/layout.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tailwind.config.cjs`

**Interfaces:**
- Consumes: `next/font/google` (`Plus_Jakarta_Sans`, `JetBrains_Mono`)
- Produces: CSS variables `--font-sans` and `--font-mono`, botanical surface utility classes (`.glass-card`, `.glass-header`, `.pill`, `.pill-active`, `.strain-indica`, `.strain-sativa`, `.strain-hybrid`, `.strain-unspecified`), mobile input zoom prevention (`16px` font on `<input>` / `<select>`), and `.cat-grid[data-active=...]` category visibility rules.

- [ ] **Step 1: Update `web/tailwind.config.cjs`**

Update `web/tailwind.config.cjs`:
```javascript
module.exports = {
  content: ['./app/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      colors: {
        slate950: '#060a0d',
        slate900: '#0d151b',
        slate850: '#121d26',
        slate800: '#182632',
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 2: Load Google Fonts in `web/app/layout.tsx` and add Viewport metadata**

Update `web/app/layout.tsx`:
```tsx
import './globals.css';
import type { Metadata, Viewport } from 'next';
import { Plus_Jakarta_Sans, JetBrains_Mono } from 'next/font/google';

const sans = Plus_Jakarta_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-sans',
  display: 'swap',
});

const mono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'TerpScout — Cheapest Cannabis $/g Near You',
  description: 'Lowest observed price per gram for flower, concentrates and vapes at Illinois dispensaries, from full menu imports.',
  icons: { icon: '/favicon.svg' },
};

export const viewport: Viewport = {
  themeColor: '#060a0d',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${sans.variable} ${mono.variable}`}>
      <body className="font-sans antialiased selection:bg-emerald-500 selection:text-slate-950">{children}</body>
    </html>
  );
}
```

- [ ] **Step 3: Modernize `web/app/globals.css`**

Update `web/app/globals.css` with the botanical dark theme, mobile-safe `16px` input sizing (`text-base sm:text-xs`), strain badge classes, and smooth scrollbars:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  * { box-sizing: border-box; }
  body {
    background-color: #060a0d;
    background-image:
      radial-gradient(ellipse 90% 45% at 50% -10%, rgba(16, 185, 129, 0.14), transparent 70%),
      radial-gradient(ellipse 60% 35% at 85% 0%, rgba(52, 211, 153, 0.06), transparent 60%);
    background-attachment: fixed;
    color: #f1f5f9;
    margin: 0;
  }
  button, a, input, select, summary { -webkit-tap-highlight-color: transparent; }
  button:disabled { cursor: not-allowed; opacity: .45; }
  input:not([type=checkbox]), select {
    @apply bg-slate-950/90 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-base sm:text-xs text-white max-w-full transition-colors focus:border-emerald-500/70;
  }
  input[type=checkbox] { accent-color: #10b981; @apply w-4 h-4 rounded; }
  button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible, [tabindex]:focus-visible {
    outline: 2px solid #34d399;
    outline-offset: 2px;
  }
}

@layer components {
  .glass-card {
    background: rgba(13, 21, 27, 0.86);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
  }
  .glass-header {
    background: rgba(6, 10, 13, 0.88);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
  .btn {
    @apply inline-flex items-center justify-center gap-1.5 rounded-xl bg-slate-800/90 border border-slate-700/80 px-3.5 py-2 text-xs font-semibold text-slate-200 transition-all hover:bg-slate-700/90 hover:border-slate-600 active:scale-[0.99];
  }
  .btn-primary {
    @apply inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-b from-emerald-400 to-emerald-500 hover:from-emerald-300 hover:to-emerald-400 text-slate-950 px-4 py-2.5 text-xs font-extrabold shadow-md shadow-emerald-950/50 transition-all active:scale-[0.99];
  }
  .selected {
    @apply bg-emerald-500 text-slate-950 border-emerald-400 shadow-sm shadow-emerald-950/60 hover:bg-emerald-400 font-bold;
  }
  .pill {
    @apply inline-flex items-center gap-1.5 shrink-0 rounded-full bg-slate-900/90 border border-slate-700/75 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-all hover:border-slate-500 hover:text-white;
  }
  .pill-active {
    @apply bg-emerald-500/20 text-emerald-300 border-emerald-400/60 shadow-sm shadow-emerald-950/50 font-bold;
  }
  .badge {
    @apply inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-950/70 border border-slate-700/70 text-[10px] font-mono leading-tight;
  }
  .strain-indica {
    @apply bg-purple-500/15 text-purple-300 border-purple-500/35;
  }
  .strain-sativa {
    @apply bg-amber-500/15 text-amber-300 border-amber-500/35;
  }
  .strain-hybrid {
    @apply bg-emerald-500/15 text-emerald-300 border-emerald-500/35;
  }
  .strain-unspecified {
    @apply bg-slate-800/80 text-slate-400 border-slate-700/60;
  }
  .brand-icon {
    @apply w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-400 via-emerald-500 to-teal-600 flex items-center justify-center text-slate-950 shadow-lg shadow-emerald-950/70 border border-emerald-300/40 shrink-0;
  }
  .field {
    @apply flex flex-col gap-1.5 text-xs font-semibold text-slate-300;
  }
  .category-art {
    background-size: cover;
    background-position: center;
  }
  .calculator-result {
    @apply bg-slate-950/90 border border-slate-800/80 p-3.5 rounded-xl text-slate-400 text-xs;
  }
  .calculator-result strong {
    @apply block text-xl text-emerald-300 font-mono font-extrabold mt-1;
  }
}

.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

@media (max-width: 1023px) {
  .cat-grid[data-active="concentrate"] > section:not([data-cat="concentrate"]),
  .cat-grid[data-active="flower"] > section:not([data-cat="flower"]),
  .cat-grid[data-active="vapes"] > section:not([data-cat="vapes"]) {
    display: none;
  }
}
```

- [ ] **Step 4: Verify `npm run typecheck` passes**

Run:
```powershell
cd web; npm run typecheck
```
Expected: Exits 0.

- [ ] **Step 5: Commit**

```powershell
git add web/tailwind.config.cjs web/app/layout.tsx web/app/globals.css
git commit -m "Configure Plus Jakarta Sans and JetBrains Mono fonts and botanical dark theme"
```

---

### Task 4: Out-The-Door (OTD) & Illinois Tax Calculator Component (`web/app/calculator.tsx`)

**Files:**
- Create: `web/app/calculator.tsx`

**Interfaces:**
- Consumes: `TAX_PRESETS`, `calculateOtd`, `inferTaxRate` from `@/lib/calculator`
- Produces:
  - `openCalculator(offer?: CalcSeed): void` — dispatches a custom browser event `'terpscout:open-calc'` so any component (`LocationControl` header button or any `OfferCard`) can open the calculator modal with optional pre-populated offer data.
  - `CalculatorModal` default export — client component rendered once in `page.tsx`.

- [ ] **Step 1: Create `web/app/calculator.tsx`**

Create `web/app/calculator.tsx`:
```tsx
'use client';
import { useEffect, useState } from 'react';
import { TAX_PRESETS, calculateOtd, inferTaxRate } from '@/lib/calculator';

export interface CalcSeed {
  name?: string;
  brand?: string | null;
  store_name?: string;
  price?: string | number | null;
  weight_grams?: string | number | null;
  category?: string | null;
  license_type?: string | null;
  flower_grade?: string | null;
  thc_pct?: string | null;
}

const EVENT_NAME = 'terpscout:open-calc';

export function openCalculator(seed?: CalcSeed) {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: seed ?? null }));
  }
}

const money = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);

const MASS_PRESETS = ['0.5', '1', '3.5', '7', '14', '28'] as const;
const DISCOUNT_PRESETS = ['0', '10', '15', '20', '25', '30'] as const;

export default function CalculatorModal() {
  const [open, setOpen] = useState(false);
  const [seed, setSeed] = useState<CalcSeed | null>(null);
  const [price, setPrice] = useState('30');
  const [weight, setWeight] = useState('3.5');
  const [discount, setDiscount] = useState('0');
  const [tax, setTax] = useState('22');

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<CalcSeed | null>).detail;
      setSeed(detail ?? null);
      if (detail) {
        if (detail.price != null && detail.price !== '') setPrice(String(detail.price));
        if (detail.weight_grams != null && detail.weight_grams !== '') setWeight(String(detail.weight_grams));
        setTax(String(inferTaxRate(detail)));
      }
      setOpen(true);
    };
    window.addEventListener(EVENT_NAME, handler);
    return () => window.removeEventListener(EVENT_NAME, handler);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (!open) return null;

  const result = calculateOtd({
    price: Number(price),
    weight: Number(weight),
    discountPct: Number(discount),
    taxPct: Number(tax),
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/75 backdrop-blur-sm p-0 sm:p-4"
      onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Out-The-Door Price and Tax Calculator"
        className="glass-card w-full sm:max-w-lg rounded-t-3xl sm:rounded-2xl p-5 space-y-4 max-h-[92dvh] overflow-y-auto border-t sm:border border-emerald-500/30"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <span className="badge text-emerald-300 border-emerald-500/30 uppercase tracking-wider">Illinois OTD Estimator</span>
            <h2 className="text-base font-extrabold text-white mt-1">Out-The-Door ($/g) Calculator</h2>
            {seed?.name ? (
              <p className="text-xs text-emerald-300 mt-0.5 line-clamp-1">
                Pre-filled: <strong>{seed.name}</strong>{seed.store_name ? ` · ${seed.store_name}` : ''}
              </p>
            ) : (
              <p className="text-xs text-slate-400 mt-0.5">
                Estimate post-discount and post-tax checkout totals.
              </p>
            )}
          </div>
          <button
            type="button"
            className="btn px-2.5 py-1.5 text-slate-300"
            aria-label="Close calculator"
            onClick={() => setOpen(false)}
          >
            ✕
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="field">
            Menu Price ($)
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          </label>
          <label className="field">
            Package Mass (g)
            <input
              type="number"
              inputMode="decimal"
              min="0.01"
              step="any"
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
            />
          </label>
          <label className="field">
            Discount (%)
            <input
              type="number"
              inputMode="decimal"
              min="0"
              max="100"
              step="any"
              value={discount}
              onChange={(e) => setDiscount(e.target.value)}
            />
          </label>
          <label className="field">
            Est. Combined Tax (%)
            <input
              type="number"
              inputMode="decimal"
              min="0"
              max="100"
              step="any"
              value={tax}
              onChange={(e) => setTax(e.target.value)}
            />
          </label>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] font-semibold text-slate-400 mr-1">Mass:</span>
            {MASS_PRESETS.map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setWeight(g)}
                className={`pill !px-2.5 !py-1 !text-[11px] font-mono ${weight === g ? 'pill-active' : ''}`}
              >
                {g}g
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] font-semibold text-slate-400 mr-1">Discount:</span>
            {DISCOUNT_PRESETS.map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDiscount(d)}
                className={`pill !px-2.5 !py-1 !text-[11px] font-mono ${discount === d ? 'pill-active' : ''}`}
              >
                {d}%
              </button>
            ))}
          </div>

          <div className="space-y-1.5 pt-1">
            <span className="text-[11px] font-semibold text-slate-400 block">Illinois Tax Presets (Excise + Local):</span>
            <div className="grid grid-cols-2 gap-1.5">
              {TAX_PRESETS.map((preset) => {
                const active = Number(tax) === preset.rate;
                return (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => setTax(String(preset.rate))}
                    className={`text-left rounded-xl p-2 border transition-all ${
                      active
                        ? 'bg-emerald-500/20 border-emerald-400/60 text-emerald-200'
                        : 'bg-slate-900/80 border-slate-800 text-slate-300 hover:border-slate-700'
                    }`}
                  >
                    <div className="text-xs font-bold">{preset.shortLabel}</div>
                    <div className="text-[10px] text-slate-400 leading-tight mt-0.5">{preset.detail}</div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {result.valid ? (
          <div className="grid grid-cols-3 gap-2.5 pt-1" aria-live="polite">
            <div className="calculator-result">
              <span className="block text-[10px] uppercase tracking-wider text-slate-400">Pre-Tax $/g</span>
              <strong>{money(result.preTaxPerGram)}</strong>
              <span className="text-[10px] font-mono text-slate-500">Sub: {money(result.discountedSubtotal)}</span>
            </div>
            <div className="calculator-result border-emerald-500/40 bg-emerald-950/20">
              <span className="block text-[10px] uppercase tracking-wider text-emerald-300 font-semibold">Est. OTD Total</span>
              <strong className="!text-emerald-300">{money(result.outTheDoorTotal)}</strong>
              <span className="text-[10px] font-mono text-slate-400">+{tax}% tax</span>
            </div>
            <div className="calculator-result">
              <span className="block text-[10px] uppercase tracking-wider text-slate-400">Est. OTD $/g</span>
              <strong>{money(result.outTheDoorPerGram)}</strong>
              <span className="text-[10px] font-mono text-slate-500">{weight}g pack</span>
            </div>
          </div>
        ) : (
          <p role="alert" className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-xl p-3">
            Enter a non-negative price, a positive gram mass, and percentages between 0 and 100.
          </p>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Run `npm run typecheck` in `web/`**

Run:
```powershell
cd web; npm run typecheck
```
Expected: Exits 0.

- [ ] **Step 3: Commit**

```powershell
git add web/app/calculator.tsx
git commit -m "Add Illinois Out-The-Door tax and $/g calculator modal"
```

---

### Task 5: Compact Sticky Command Bar & Collapsible Location Drawer (`web/app/location.tsx`) and Instant Filter Strip (`web/app/filters.tsx`)

**Files:**
- Modify: `web/app/location.tsx`
- Create: `web/app/filters.tsx`

**Interfaces:**
- Consumes: `openCalculator` from `./calculator`, `GRADES`, `STRAINS`, `SIZES` from `@/lib/deals`
- Produces:
  - `LocationControl`: Renders the compact sticky command header (Brand + Location Pill `📍 {place} · {radius} mi ▾` + `Rec`/`Med` segmented switch + `🧮 OTD` button) and collapsible Location Drawer with GPS, ZIP/city input, Illinois quick hubs, and radius pills.
  - `FilterStrip`: Renders the instant search bar, `Filters` popover button (with active badge count for `grade`, `bogo`, `stale`, `unverified`), Strain Type pill rail (`All`, `Indica`, `Sativa`, `Hybrid`), and Package Size pill rail (`Any`, `0.5g`, `1g`, `3.5g`, `7g`, `14g`, `28g`).

- [ ] **Step 1: Redesign `web/app/location.tsx` as Compact Sticky Command Header + Collapsible Location Drawer**

Update `web/app/location.tsx`:
```tsx
'use client';
import { useEffect, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { openCalculator } from './calculator';

const KEY = 'terpscout.origin';
const RKEY = 'terpscout.radius';
type Pick = { lat: number; lon: number; place: string };

const QUICK_HUBS: readonly [string, string][] = [
  ['Peoria', '61602'],
  ['Normal', '61761'],
  ['Champaign', '61820'],
  ['Springfield', '62701'],
  ['Chicago', '60601'],
  ['Rockford', '61101'],
  ['Streator', '61358'],
];

const RADII = [5, 10, 25, 50, 100, 200] as const;

export default function LocationControl({
  active,
  radius,
  place,
  license = 'recreational',
  dataVersion,
}: {
  active: boolean;
  radius: number;
  place: string;
  license?: string;
  dataVersion?: string;
}) {
  const router = useRouter();
  const sp = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [open, setOpen] = useState(!place);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState('');

  const pushUrl = (u: URLSearchParams) => {
    ['p_concentrate', 'p_flower', 'p_vapes'].forEach((k) => u.delete(k));
    startTransition(() => {
      router.push(`/?${u.toString()}`);
    });
  };

  const go = (o: Pick) => {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch {}
    const u = new URLSearchParams(sp.toString());
    u.set('lat', o.lat.toFixed(5));
    u.set('lon', o.lon.toFixed(5));
    u.set('place', o.place);
    u.delete('region');
    try {
      const r = localStorage.getItem(RKEY);
      if (r && !u.get('radius')) u.set('radius', r);
    } catch {}
    setOpen(false);
    pushUrl(u);
  };

  useEffect(() => {
    if (sp.get('lat') || sp.get('region')) return;
    try {
      const o = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (o && Number.isFinite(o.lat) && Number.isFinite(o.lon)) go(o);
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const gps = () => {
    setMsg('');
    if (!navigator.geolocation) {
      setMsg('Location is not available in this browser. Enter a ZIP or city.');
      return;
    }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setBusy(false);
        go({ lat: p.coords.latitude, lon: p.coords.longitude, place: 'Your location (GPS)' });
      },
      (e) => {
        setBusy(false);
        setMsg(`Could not get your location (${e.message}). Enter a ZIP or city.`);
      },
      { timeout: 15000, maximumAge: 60000 }
    );
  };

  const resolveQuery = async (query: string) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setMsg('');
    setBusy(true);
    try {
      const r = await fetch(`/api/v1/geocode?q=${encodeURIComponent(trimmed)}`);
      const j = await r.json();
      if (!r.ok) setMsg(j?.detail?.message || 'Lookup failed');
      else go({ lat: j.latitude, lon: j.longitude, place: j.label });
    } catch {
      setMsg('Lookup failed; try again');
    }
    setBusy(false);
  };

  const lookup = async (e: React.FormEvent) => {
    e.preventDefault();
    await resolveQuery(text);
  };

  const setRadius = (v: string) => {
    const u = new URLSearchParams(sp.toString());
    u.set('radius', v);
    try { localStorage.setItem(RKEY, v); } catch {}
    pushUrl(u);
  };

  const setLicense = (nextLicense: 'recreational' | 'medicinal') => {
    const u = new URLSearchParams(sp.toString());
    u.set('license', nextLicense);
    pushUrl(u);
  };

  const clear = () => {
    try { localStorage.removeItem(KEY); } catch {}
    setOpen(false);
    startTransition(() => {
      router.push('/');
    });
  };

  const allRadii = [...new Set([...RADII, radius])].sort((a, b) => a - b);

  return (
    <header className="glass-header sticky top-0 z-40 -mx-3 px-3 sm:mx-0 sm:px-4 sm:rounded-2xl sm:border sm:border-white/10 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {/* Brand Identity */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="brand-icon" aria-hidden="true">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.3" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v18m0-18c-3.5 3-6 6.5-6 10.5A6 6 0 0012 19.5a6 6 0 006-6C18 9.5 15.5 6 12 3z" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <h1 className="font-extrabold text-base sm:text-lg tracking-tight text-white leading-none">TerpScout</h1>
              <span className="badge text-emerald-300 border-emerald-500/30 hidden xs:inline-flex">$/g</span>
              {isPending && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" aria-label="Updating deals" />}
            </div>
            <p className="text-[10px] text-slate-400 truncate">
              Illinois Dispensary $/g Finder{dataVersion ? ` · v${dataVersion}` : ''}
            </p>
          </div>
        </div>

        {/* Interactive Controls: Location Pill + Rec/Med Switch + OTD Calc */}
        <div className="flex items-center gap-1.5 ml-auto">
          <button
            type="button"
            aria-expanded={open}
            aria-label="Change search location and distance radius"
            onClick={() => setOpen((v) => !v)}
            className={`pill !py-1.5 !px-2.5 max-w-[190px] sm:max-w-xs ${open ? 'pill-active' : ''}`}
          >
            <span aria-hidden="true">📍</span>
            <span className="truncate font-semibold text-white">
              {place ? place.replace(/, USA$/, '') : 'Set location'}
            </span>
            <span className="font-mono text-[11px] text-emerald-300 shrink-0">· {radius}mi</span>
            <span className="text-[10px] text-slate-400 shrink-0">{open ? '▴' : '▾'}</span>
          </button>

          <div
            role="group"
            aria-label="License channel"
            className="inline-flex rounded-full bg-slate-950/90 border border-slate-700/80 p-0.5 text-xs"
          >
            {(['recreational', 'medicinal'] as const).map((l) => {
              const selected = license === l;
              return (
                <button
                  key={l}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setLicense(l)}
                  className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors ${
                    selected ? 'bg-emerald-500 text-slate-950' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {l === 'recreational' ? 'Rec' : 'Med'}
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={() => openCalculator()}
            className="pill !py-1.5 !px-2.5 text-emerald-300 border-emerald-500/30 hover:border-emerald-400"
            aria-label="Open Out-The-Door tax and $/g calculator"
          >
            <span aria-hidden="true">🧮</span>
            <span className="hidden sm:inline">OTD Calc</span>
          </button>
        </div>
      </div>

      {/* Expandable Location Drawer */}
      {open && (
        <section
          aria-label="Search location"
          className="mt-3 pt-3 border-t border-slate-800/90 space-y-3 animate-in fade-in duration-150"
        >
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="button"
              className="btn-primary py-2.5 text-xs sm:w-auto shrink-0"
              onClick={gps}
              disabled={busy}
            >
              {busy ? 'Locating…' : '📍 Use my current location'}
            </button>

            <form onSubmit={lookup} className="flex gap-2 flex-1">
              <label htmlFor="loc-text" className="sr-only">
                Or enter a ZIP code or city
              </label>
              <input
                id="loc-text"
                className="min-w-0 flex-1 !py-2"
                placeholder="Enter ZIP or City (e.g. 61602 or Peoria, IL)"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <button type="submit" className="btn-primary px-4" disabled={busy || !text.trim()}>
                Set
              </button>
            </form>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
              <span className="text-[11px] font-semibold text-slate-400 shrink-0">Quick IL Hubs:</span>
              {QUICK_HUBS.map(([label, zip]) => (
                <button
                  key={zip}
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setText(zip);
                    void resolveQuery(zip);
                  }}
                  className="pill !px-2.5 !py-1 !text-[11px]"
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1.5 flex-wrap">
              <label htmlFor="radius-select" className="text-[11px] font-semibold text-slate-400">
                Range:
              </label>
              <select
                id="radius-select"
                aria-label="Search range in miles"
                className="!py-1.5 !px-2.5 !rounded-lg font-mono"
                value={radius}
                onChange={(e) => setRadius(e.target.value)}
              >
                {allRadii.map((m) => (
                  <option key={m} value={m}>
                    Within {m} miles
                  </option>
                ))}
              </select>
              {active && (
                <button type="button" className="btn !py-1.5 !px-2.5 text-[11px]" onClick={clear}>
                  Reset
                </button>
              )}
            </div>
          </div>

          {msg && (
            <p role="alert" className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2">
              {msg}
            </p>
          )}
        </section>
      )}
    </header>
  );
}
```

- [ ] **Step 2: Create `web/app/filters.tsx` for Instant Search, Pill Rails & Filter Sheet**

Create `web/app/filters.tsx`:
```tsx
'use client';
import { useEffect, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { GRADES, STRAINS } from '@/lib/deals';

const SIZE_OPTIONS: readonly { value: string; label: string }[] = [
  { value: 'any', label: 'Any Size' },
  { value: '0.5', label: '0.5g' },
  { value: '1', label: '1g' },
  { value: '3.5', label: '3.5g (⅛)' },
  { value: '7', label: '7g (¼)' },
  { value: '14', label: '14g (½)' },
  { value: '28', label: '28g (1 oz)' },
];

const GRADE_LABELS: Record<string, string> = {
  whole: 'Whole Flower',
  smalls: 'Smalls / Popcorn',
  shake: 'Shake / Ground',
  infused: 'Infused',
  all: 'All Flower Grades',
};

const STRAIN_STYLES: Record<string, string> = {
  Indica: 'strain-indica border-purple-400/60',
  Sativa: 'strain-sativa border-amber-400/60',
  Hybrid: 'strain-hybrid border-emerald-400/60',
};

export default function FilterStrip({
  q,
  grade,
  strain,
  size,
  bogo,
  stale,
  unverified,
}: {
  q: string;
  grade: string;
  strain: string;
  size: string;
  bogo: boolean;
  stale: boolean;
  unverified: boolean;
}) {
  const router = useRouter();
  const sp = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [search, setSearch] = useState(q);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    setSearch(q);
  }, [q]);

  const updateParams = (updates: Record<string, string | null>) => {
    const u = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v == null || v === '' || (k === 'grade' && v === 'whole') || (k === 'size' && v === 'any')) {
        u.delete(k);
      } else {
        u.set(k, v);
      }
    }
    ['p_concentrate', 'p_flower', 'p_vapes'].forEach((k) => u.delete(k));
    startTransition(() => {
      router.push(`/?${u.toString()}`);
    });
  };

  useEffect(() => {
    if (search === q) return;
    const timer = setTimeout(() => {
      updateParams({ q: search.trim() || null });
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, q]);

  const extraFilterCount =
    (grade !== 'whole' ? 1 : 0) +
    (bogo ? 1 : 0) +
    (stale ? 1 : 0) +
    (unverified ? 1 : 0);

  const hasAnyFilter =
    Boolean(q) ||
    grade !== 'whole' ||
    Boolean(strain) ||
    (size && size !== 'any') ||
    bogo ||
    stale ||
    unverified;

  const resetAll = () => {
    setSearch('');
    updateParams({
      q: null,
      grade: null,
      strain: null,
      size: null,
      promo: null,
      stale: null,
      unverified: null,
    });
  };

  return (
    <section aria-label="Deal filters" className="glass-card rounded-2xl p-3 space-y-2.5">
      {/* Row 1: Search Input + Advanced Filters Button */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs" aria-hidden="true">
            🔍
          </span>
          <input
            type="search"
            aria-label="Search deals by product, brand, or dispensary"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search strain, brand, or dispensary…"
            maxLength={300}
            className="w-full !pl-8 !pr-8 !py-2"
          />
          {search && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => {
                setSearch('');
                updateParams({ q: null });
              }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white text-xs px-1"
            >
              ✕
            </button>
          )}
        </div>

        <button
          type="button"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen((v) => !v)}
          className={`btn shrink-0 !py-2 ${extraFilterCount > 0 || drawerOpen ? 'border-emerald-400/60 text-emerald-300 bg-emerald-500/15' : ''}`}
        >
          <span>⚙ Filters</span>
          {extraFilterCount > 0 && (
            <span className="rounded-full bg-emerald-400 text-slate-950 px-1.5 py-0.2 text-[10px] font-extrabold font-mono">
              {extraFilterCount}
            </span>
          )}
        </button>

        {hasAnyFilter && (
          <button
            type="button"
            onClick={resetAll}
            className="btn shrink-0 !py-2 text-slate-400 hover:text-white hidden sm:inline-flex"
          >
            Reset
          </button>
        )}
      </div>

      {/* Row 2: Strain Type & Package Size Horizontal Pill Rails */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2">
        {/* Strain Type Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5" role="group" aria-label="Filter by strain type">
          <button
            type="button"
            aria-pressed={!strain}
            onClick={() => updateParams({ strain: null })}
            className={`pill !py-1 !px-2.5 !text-[11px] ${!strain ? 'pill-active' : ''}`}
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
                className={`pill !py-1 !px-2.5 !text-[11px] ${active ? STRAIN_STYLES[s] + ' font-bold' : ''}`}
              >
                {s}
              </button>
            );
          })}
        </div>

        <span className="hidden sm:inline text-slate-700" aria-hidden="true">|</span>

        {/* Package Size Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5" role="group" aria-label="Filter by package size">
          {SIZE_OPTIONS.map((opt) => {
            const active = (size || 'any') === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                aria-pressed={active}
                onClick={() => updateParams({ size: opt.value === 'any' ? null : opt.value })}
                className={`pill !py-1 !px-2.5 !text-[11px] font-mono ${active ? 'pill-active' : ''}`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Expandable Advanced Filters Drawer */}
      {drawerOpen && (
        <div className="pt-2.5 border-t border-slate-800/90 space-y-3 animate-in fade-in duration-150">
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
              Flower Grade
            </span>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Flower grade">
              {GRADES.map((g) => {
                const active = grade === g;
                return (
                  <button
                    key={g}
                    type="button"
                    aria-pressed={active}
                    onClick={() => updateParams({ grade: g })}
                    className={`pill !py-1 !px-3 !text-xs ${active ? 'pill-active' : ''}`}
                  >
                    {GRADE_LABELS[g] ?? g}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="flex flex-wrap gap-4 text-xs text-slate-300">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={bogo}
                  onChange={(e) => updateParams({ promo: e.target.checked ? 'bogo' : null })}
                />
                <span>BOGO promotions only</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={unverified}
                  onChange={(e) => updateParams({ unverified: e.target.checked ? '1' : null })}
                />
                <span>Include unverified totals</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={stale}
                  onChange={(e) => updateParams({ stale: e.target.checked ? '1' : null })}
                />
                <span>Include stale menus (&gt;12h)</span>
              </label>
            </div>

            {hasAnyFilter && (
              <button type="button" onClick={resetAll} className="btn !py-1.5 !px-3 text-xs">
                Reset all filters
              </button>
            )}
          </div>
        </div>
      )}

      {isPending && (
        <div className="h-0.5 w-full bg-slate-800 overflow-hidden rounded-full" role="status" aria-label="Updating deals">
          <div className="h-full w-1/2 bg-emerald-400 animate-pulse" />
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Verify `npm run typecheck` passes**

Run:
```powershell
cd web; npm run typecheck
```
Expected: Exits 0.

- [ ] **Step 4: Commit**

```powershell
git add web/app/location.tsx web/app/filters.tsx
git commit -m "Redesign LocationControl header pill and add instant FilterStrip component"
```

---

### Task 6: Mobile-First Category Tabs (`web/app/categories.tsx`), Botanical Deal Cards (`web/app/offer-card.tsx`), and Main Deals Page (`web/app/page.tsx`)

**Files:**
- Modify: `web/app/categories.tsx`
- Create: `web/app/offer-card.tsx`
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: `LocationControl`, `FilterStrip`, `CalculatorModal`, `openCalculator`, `CATEGORIES`, `GRADES`, `LICENSES`, `STRAINS`, `queryDeals`, `regions`, `sizeForCategory`, `strainBucket`, `type Offer`
- Produces:
  - `CategoryGrid`: Sticky mobile category tab switcher defaulting to `'flower'` (instead of stacking all 3 categories), with category icons, accent bars, and counts.
  - `OfferCard`: Botanical deal card with hero `$ / g` badge, strikethrough regular price when on sale, color-coded strain badges (`Indica`/`Sativa`/`Hybrid`), grouped `StrainList` accordion, tactile `View on Menu ↗` CTA, and 1-tap `🧮 OTD` calculator pre-fill button.
  - `Home` (`web/app/page.tsx`): Server component reading `region`, `lat`/`lon`/`radius`/`place`, `license`, `grade`, `strain`, `size`, `q`, `stale`, `unverified`, `promo`, and per-category page numbers `p_concentrate`/`p_flower`/`p_vapes`.

- [ ] **Step 1: Update `web/app/categories.tsx` to default to `'flower'` on mobile with category accents**

Update `web/app/categories.tsx`:
```tsx
'use client';
import { useEffect, useState, type ReactNode } from 'react';

const KEY = 'terpscout.category';
type Chip = { id: string; label: string; total: number; color: string };

const ICONS: Record<string, string> = {
  flower: '🌿',
  concentrate: '🍯',
  vapes: '💨',
  all: '⚡',
};

// Below the lg breakpoint the three category columns stack; the chips show one category (defaulting to flower) or all at a time. Desktop always shows every column.
export default function CategoryGrid({ chips, children }: { chips: Chip[]; children: ReactNode }) {
  const [active, setActive] = useState('flower');

  useEffect(() => {
    try {
      const v = localStorage.getItem(KEY);
      if (v && (v === 'all' || chips.some((c) => c.id === v))) setActive(v);
    } catch {}
  }, [chips]);

  const pick = (id: string) => {
    setActive(id);
    try { localStorage.setItem(KEY, id); } catch {}
  };

  // Order mobile tabs with Flower first (most popular mobile starting tab), then Concentrate, Vapes, and All.
  const ordered = [
    ...chips.filter((c) => c.id === 'flower'),
    ...chips.filter((c) => c.id !== 'flower'),
    { id: 'all', label: 'All', total: chips.reduce((sum, c) => sum + c.total, 0), color: '#10b981' },
  ];

  return (
    <>
      <nav
        aria-label="Category"
        className="lg:hidden sticky top-[53px] z-30 -mx-3 px-3 py-2 flex gap-2 overflow-x-auto no-scrollbar bg-[#060a0d]/95 backdrop-blur-md border-b border-slate-800/90"
      >
        {ordered.map((c) => {
          const isSelected = active === c.id;
          return (
            <button
              key={c.id}
              type="button"
              aria-pressed={isSelected}
              onClick={() => pick(c.id)}
              style={isSelected ? { borderColor: c.color } : undefined}
              className={`btn shrink-0 capitalize !py-2 !px-3.5 rounded-xl transition-all ${
                isSelected ? 'selected' : 'text-slate-300'
              }`}
            >
              <span aria-hidden="true">{ICONS[c.id] ?? '🌿'}</span>
              <span>{c.label}</span>
              {c.total >= 0 && (
                <span className={`font-mono text-[11px] px-1.5 py-0.2 rounded-md ${isSelected ? 'bg-slate-950/25 text-slate-950 font-extrabold' : 'bg-slate-950/70 text-slate-400'}`}>
                  {c.total}
                </span>
              )}
            </button>
          );
        })}
      </nav>
      <div className="cat-grid grid gap-4 lg:grid-cols-3 items-start" data-active={active}>
        {children}
      </div>
    </>
  );
}
```

- [ ] **Step 2: Create `web/app/offer-card.tsx` with Hero Price Callout, Semantic Strain Badges & 1-Tap OTD Button**

Create `web/app/offer-card.tsx`:
```tsx
'use client';
import { openCalculator } from './calculator';
import { strainBucket, type Offer } from '@/lib/deals';

const BUCKETS = ['Indica', 'Sativa', 'Hybrid', 'Unspecified'] as const;

const BUCKET_BADGE: Record<(typeof BUCKETS)[number], string> = {
  Indica: 'strain-indica',
  Sativa: 'strain-sativa',
  Hybrid: 'strain-hybrid',
  Unspecified: 'strain-unspecified',
};

const money = (v: string | null | undefined) =>
  v == null || v === ''
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

const when = (v: string) =>
  new Date(v).toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    dateStyle: 'short',
    timeStyle: 'short',
  });

const safeUrl = (v?: string | null) => {
  try {
    const u = new URL(v ?? '');
    return ['https:', 'http:'].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
};

function StrainList({ o }: { o: Offer }) {
  const vs = o.variants ?? [];
  return (
    <details className="group rounded-xl bg-slate-950/70 border border-slate-800/90 px-3 py-2 text-xs">
      <summary className="cursor-pointer font-semibold text-emerald-300 flex items-center justify-between select-none">
        <span>🌿 {vs.length} strains at this price — show list</span>
        <span className="text-[10px] text-slate-400 group-open:rotate-180 transition-transform">▾</span>
      </summary>
      <div className="mt-2.5 pt-2 border-t border-slate-800/80 space-y-2.5">
        {BUCKETS.map((b) => {
          const list = vs
            .filter((v) => strainBucket(v.strain_type) === b)
            .sort((x, y) => x.name.localeCompare(y.name));
          if (list.length === 0) return null;
          return (
            <div key={b} className="space-y-1">
              <div className="flex items-center gap-1.5">
                <span className={`badge ${BUCKET_BADGE[b]} uppercase tracking-wider font-sans font-bold`}>
                  {b}
                </span>
                <span className="text-[10px] font-mono text-slate-500">{list.length}</span>
              </div>
              <ul className="grid gap-1 sm:grid-cols-2 lg:grid-cols-1">
                {list.map((v) => {
                  const u = safeUrl(v.source_url);
                  return (
                    <li
                      key={v.id}
                      className="flex items-center justify-between gap-2 rounded-lg bg-slate-900/70 px-2.5 py-1.5 text-[11px]"
                    >
                      {u ? (
                        <a
                          className="text-slate-100 font-medium underline decoration-slate-600 hover:text-emerald-300 truncate"
                          href={u}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {v.name} ↗
                        </a>
                      ) : (
                        <span className="text-slate-200 truncate">{v.name}</span>
                      )}
                      {v.thc_pct && (
                        <span className="text-[10px] font-mono text-slate-400 shrink-0">
                          {v.thc_pct}% THC
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </details>
  );
}

export default function OfferCard({ o, rank }: { o: Offer; rank?: number }) {
  const href = safeUrl(o.source_url);
  const grouped = (o.variants?.length ?? 0) > 1;
  const bucket = strainBucket(o.strain_type);
  const massLabel = o.weight_label || (o.weight_grams ? `${o.weight_grams}g` : 'mass unknown');
  const hasDiscount =
    o.regular_price != null &&
    o.effective_price != null &&
    Number(o.regular_price) > Number(o.effective_price);

  return (
    <article className="rounded-2xl border border-slate-700/60 hover:border-slate-600/80 bg-slate-900/90 p-3.5 space-y-2.5 transition-colors shadow-sm">
      {/* Top Row: Identity & Hero $/g Metric */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            {rank != null && rank <= 3 && (
              <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-extrabold">
                #{rank}
              </span>
            )}
            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400/90 truncate">
              {o.brand || 'Brand not supplied'}
            </span>
          </div>
          <h3 className="text-sm font-bold text-white leading-snug break-words">
            {grouped ? `${o.brand || 'Assorted'} · ${o.variants!.length} strains` : o.name}
          </h3>

          {/* Badges Row */}
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
            {!grouped && o.strain_type && (
              <span className={`badge ${BUCKET_BADGE[bucket]} font-sans font-semibold`}>
                {o.strain_type}
              </span>
            )}
            {o.flower_grade && o.flower_grade !== 'whole' && (
              <span className="badge bg-amber-500/15 text-amber-200 border-amber-500/30 capitalize font-sans font-medium">
                {o.flower_grade}
              </span>
            )}
            <span className="badge text-slate-200 bg-slate-950/80">{massLabel}</span>
            {!grouped && o.thc_pct && (
              <span className="badge text-slate-300">THC {o.thc_pct}%</span>
            )}
          </div>
        </div>

        {/* Hero Price Box */}
        <div className="text-right shrink-0 bg-slate-950/80 border border-slate-800/90 rounded-xl px-2.5 py-1.5">
          <p className="text-lg sm:text-xl font-extrabold font-mono text-emerald-400 leading-none">
            {money(o.price_per_gram)}
            <span className="text-[10px] font-normal text-slate-400">/g</span>
          </p>
          <p className="text-[11px] font-mono text-slate-200 mt-1">
            {hasDiscount && (
              <s className="text-slate-500 mr-1 text-[10px]">{money(o.regular_price)}</s>
            )}
            <span className="font-bold">{money(o.effective_price)}</span>
          </p>
        </div>
      </div>

      {/* Store & Observation Metadata */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-800/70 text-xs">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-slate-200 font-semibold truncate">{o.store_name}</span>
          <span className="badge text-emerald-300 border-emerald-500/30 shrink-0">
            {o.distance_miles.toFixed(1)} mi
          </span>
          <span className="text-[10px] uppercase tracking-wider text-slate-400 shrink-0">
            {o.license_type === 'medicinal' ? 'Med' : 'Rec'}
          </span>
        </div>

        <span
          className={`badge ${
            o.completeness === 'B' || o.freshness !== 'fresh'
              ? 'text-amber-300 border-amber-500/30'
              : 'text-emerald-300 border-emerald-500/30'
          }`}
        >
          {o.completeness === 'B' ? 'unverified total' : o.freshness}
        </span>
      </div>

      <p className="text-[10px] text-slate-400">
        Observed {when(o.last_seen_at)}
        {o.conditional ? ' · Conditional promotion' : ''}
      </p>

      {/* Grouped Strains List */}
      {grouped && <StrainList o={o} />}

      {/* Bottom Action Row: Menu Link + 1-Tap OTD Calculator */}
      <div className="flex items-center gap-2 pt-0.5">
        {href ? (
          <a
            className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/35 px-3 py-2 text-xs font-bold text-emerald-300 transition-colors"
            href={href}
            target="_blank"
            rel="noopener noreferrer"
          >
            <span>View on dispensary menu</span>
            <span aria-hidden="true">↗</span>
          </a>
        ) : (
          <span className="flex-1 text-[11px] text-slate-500 py-1">Menu link unavailable</span>
        )}
        <button
          type="button"
          onClick={() =>
            openCalculator({
              name: grouped ? `${o.brand || 'Offer'} (${massLabel})` : o.name,
              brand: o.brand,
              store_name: o.store_name,
              price: o.effective_price,
              weight_grams: o.weight_grams,
              category: o.category,
              license_type: o.license_type,
              flower_grade: o.flower_grade,
              thc_pct: o.thc_pct,
            })
          }
          className="btn !py-2 !px-3 text-slate-300 hover:text-emerald-300 shrink-0"
          aria-label={`Estimate Out-The-Door price for ${o.name}`}
          title="Estimate Out-The-Door price with tax & discounts"
        >
          🧮 OTD
        </button>
      </div>
    </article>
  );
}
```

- [ ] **Step 3: Update `web/app/page.tsx` to integrate `LocationControl`, `FilterStrip`, `OfferCard`, `CategoryGrid`, and `CalculatorModal`**

Update `web/app/page.tsx`:
```tsx
import LocationControl from './location';
import FilterStrip from './filters';
import CategoryGrid from './categories';
import OfferCard from './offer-card';
import CalculatorModal from './calculator';
import { parseOrigin } from '@/lib/origin';
import {
  CATEGORIES,
  GRADES,
  LICENSES,
  SIZES,
  STRAINS,
  queryDeals,
  regions,
  sizeForCategory,
} from '@/lib/deals';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 20;
const ACCENT: Record<string, string> = {
  concentrate: '#fbbf24',
  flower: '#34d399',
  vapes: '#c084fc',
};
type Search = Record<string, string | string[] | undefined>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';
const money = (v: string | null | undefined) =>
  v == null || v === ''
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(v));

export default async function Home({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const reg = await regions();
  const regionId = one(sp.region) || reg.active_region_id || reg.items[0]?.id || '';
  const origin = parseOrigin((k) => one(sp[k]) || null);
  const license = LICENSES.includes(one(sp.license) as never) ? one(sp.license) : 'recreational';
  const grade = GRADES.includes(one(sp.grade) as never) ? one(sp.grade) : 'whole';
  const strainRaw = one(sp.strain);
  const strain = STRAINS.find((s) => s.toLowerCase() === strainRaw.toLowerCase()) ?? '';
  const sizeRaw = one(sp.size);
  const size = SIZES.includes(sizeRaw as never) ? sizeRaw : 'any';
  const q = one(sp.q).slice(0, 300);
  const stale = one(sp.stale) === '1';
  const unverified = one(sp.unverified) === '1';
  const bogo = one(sp.promo) === 'bogo';
  const cats = CATEGORIES;
  const pages = Object.fromEntries(
    cats.map((c) => [c, Math.max(1, Number(one(sp[`p_${c}`])) || 1)])
  );

  const results = await Promise.all(
    cats.map((category) =>
      queryDeals({
        region_id: regionId,
        origin: origin ?? undefined,
        license_type: license,
        category,
        q,
        include_stale: stale,
        include_unverified: unverified,
        flower_grade: grade,
        strain_type: strain || undefined,
        size: sizeForCategory(category, size),
        promo: bogo ? 'bogo' : undefined,
        group: true,
        page: pages[category],
        page_size: PAGE_SIZE,
      })
    )
  );

  const base = {
    ...(origin
      ? {
          lat: String(origin.latitude),
          lon: String(origin.longitude),
          radius: String(origin.radius_miles),
          place: origin.label,
        }
      : { region: regionId }),
    license,
    grade: grade !== 'whole' ? grade : '',
    strain,
    size: size !== 'any' ? size : '',
    q,
    stale: stale ? '1' : '',
    unverified: unverified ? '1' : '',
    promo: bogo ? 'bogo' : '',
  };

  const link = (category: string, page: number) => {
    const u = new URLSearchParams();
    Object.entries({
      ...base,
      ...Object.fromEntries(
        cats.map((c) => [`p_${c}`, c === category ? String(page) : String(pages[c])])
      ),
    }).forEach(([k, v]) => {
      if (v) u.set(k, v);
    });
    return `/?${u.toString()}`;
  };

  const region = origin
    ? { radius_miles: origin.radius_miles, label: origin.label }
    : reg.items.find((r) => r.id === regionId);

  return (
    <main className="max-w-7xl mx-auto px-3 sm:px-5 pb-12 sm:py-4 space-y-3">
      <LocationControl
        active={!!origin}
        radius={region?.radius_miles ?? 50}
        place={region?.label ?? ''}
        license={license}
        dataVersion={results[0]?.data_version}
      />

      <FilterStrip
        q={q}
        grade={grade}
        strain={strain}
        size={size}
        bogo={bogo}
        stale={stale}
        unverified={unverified}
      />

      {region && (
        <p className="text-[11px] text-slate-400 px-1">
          Showing <strong className="text-slate-200">{license}</strong> deals within{' '}
          <strong className="text-slate-200">{region.radius_miles} miles</strong> of{' '}
          <strong className="text-emerald-400">{region.label}</strong>. Pre-tax observed menu prices; menus older than 12h hidden unless included.
        </p>
      )}

      <CategoryGrid
        chips={cats.map((c, i) => ({
          id: c,
          label: c,
          total: results[i].total,
          color: ACCENT[c],
        }))}
      >
        {cats.map((category, i) => {
          const r = results[i];
          const last = Math.max(1, Math.ceil(r.total / PAGE_SIZE));
          const page = pages[category];
          const topDeal = r.items[0];
          const activeSize = sizeForCategory(category, size);

          return (
            <section
              key={category}
              data-cat={category}
              className="glass-card rounded-2xl overflow-hidden"
              style={{ borderColor: `${ACCENT[category]}40` }}
            >
              <div
                className="category-art relative h-24 sm:h-28"
                style={{
                  backgroundImage: `linear-gradient(to top,#060a0d 8%,rgba(6,10,13,.35)),url('/${category}.jpg')`,
                }}
              >
                <div className="absolute inset-x-4 bottom-3 flex items-end justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span
                        className="badge uppercase tracking-widest font-bold"
                        style={{ color: ACCENT[category] }}
                      >
                        {category}
                      </span>
                      {activeSize && (
                        <span className="badge text-emerald-300 border-emerald-500/40">
                          {activeSize}g
                        </span>
                      )}
                      {strain && (
                        <span className="badge text-slate-200">{strain}</span>
                      )}
                    </div>
                    <h2 className="font-extrabold text-base sm:text-lg text-white mt-1 capitalize leading-tight">
                      {category} {bogo ? 'BOGO Deals' : 'Best Deals'}
                    </h2>
                  </div>

                  {topDeal?.price_per_gram && (
                    <div className="text-right bg-slate-950/85 border border-slate-800 rounded-xl px-2.5 py-1">
                      <span className="block text-[9px] uppercase tracking-wider text-slate-400">
                        Best $/g
                      </span>
                      <span
                        className="font-mono font-extrabold text-sm"
                        style={{ color: ACCENT[category] }}
                      >
                        {money(topDeal.price_per_gram)}/g
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className="px-4 py-2 bg-slate-900/95 border-b border-slate-800/90 flex items-center justify-between text-[11px] text-slate-400">
                <span>
                  Ranked by <strong style={{ color: ACCENT[category] }}>price / gram</strong>
                </span>
                <span className="font-mono">
                  {r.total} {r.total === 1 ? 'listing' : 'listings'}
                </span>
              </div>

              <div className="p-3 space-y-2.5">
                {r.items.length === 0 ? (
                  <div className="text-center py-8 px-4 space-y-2">
                    <p className="text-xs font-semibold text-slate-300">
                      No comparable {category} offers match these filters.
                    </p>
                    <p className="text-[11px] text-slate-500">
                      Try widening your search radius, switching package size to Any Size, or clearing active filters.
                    </p>
                  </div>
                ) : (
                  r.items.map((o, idx) => (
                    <OfferCard
                      key={o.id}
                      o={o}
                      rank={(page - 1) * PAGE_SIZE + idx + 1}
                    />
                  ))
                )}
              </div>

              {r.total > PAGE_SIZE && (
                <nav
                  aria-label={`${category} pagination`}
                  className="flex justify-between items-center px-4 py-3 border-t border-slate-800/90 text-xs bg-slate-950/40"
                >
                  {page > 1 ? (
                    <a className="btn" href={link(category, page - 1)}>
                      ← Prev
                    </a>
                  ) : (
                    <span />
                  )}
                  <span className="font-mono text-slate-400">
                    Page {page} of {last}
                  </span>
                  {page < last ? (
                    <a className="btn" href={link(category, page + 1)}>
                      Next →
                    </a>
                  ) : (
                    <span />
                  )}
                </nav>
              )}
            </section>
          );
        })}
      </CategoryGrid>

      <CalculatorModal />
    </main>
  );
}
```

- [ ] **Step 4: Run `npm run typecheck`, `npm test`, and `npm run build` in `web/`**

Run:
```powershell
cd web; npm run typecheck; npm test; npm run build
```
Expected: Typecheck, unit tests, and production Next.js build all succeed with 0 errors.

- [ ] **Step 5: Commit**

```powershell
git add web/app/categories.tsx web/app/offer-card.tsx web/app/page.tsx
git commit -m "Redesign mobile category tabs, botanical OfferCard, and compact deals layout"
```
