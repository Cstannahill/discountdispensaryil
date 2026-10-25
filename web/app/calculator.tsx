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

  const resetDefaults = () => {
    setPrice('30');
    setWeight('3.5');
    setDiscount('0');
    setTax('22');
    setSeed(null);
  };

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
        {/* Mobile Pull Handle */}
        <div className="w-10 h-1 bg-slate-700/80 rounded-full mx-auto sm:hidden mb-1" aria-hidden="true" />

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
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={resetDefaults}
              className="text-xs text-slate-400 hover:text-white px-1.5 py-1"
              title="Reset inputs to default values"
            >
              Reset
            </button>
            <button
              type="button"
              className="btn px-2.5 py-1.5 text-slate-300"
              aria-label="Close calculator"
              onClick={() => setOpen(false)}
            >
              ✕
            </button>
          </div>
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

        {/* Illinois Tax Statutory Breakdown */}
        <div className="pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-slate-300">Illinois Cannabis Tax Rates</span>
            <span className="text-[10px] text-slate-500 font-mono">410 ILCS 705/65-10</span>
          </div>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[10px] text-slate-400">
            <li className="bg-slate-950/50 rounded-lg p-1.5 border border-slate-800/60">
              • <strong className="text-slate-200">Medical:</strong> 1% state retail tax (excise exempt)
            </li>
            <li className="bg-slate-950/50 rounded-lg p-1.5 border border-slate-800/60">
              • <strong className="text-slate-200">Rec Flower (≤35% THC):</strong> 10% excise + sales tax ≈ 22%
            </li>
            <li className="bg-slate-950/50 rounded-lg p-1.5 border border-slate-800/60">
              • <strong className="text-slate-200">Rec Infused Products:</strong> 20% excise + sales tax ≈ 32%
            </li>
            <li className="bg-slate-950/50 rounded-lg p-1.5 border border-slate-800/60">
              • <strong className="text-slate-200">Rec Concentrates / &gt;35% THC:</strong> 25% excise + sales tax ≈ 37%
            </li>
          </ul>
          <p className="text-[10px] text-slate-500 leading-tight">
            *Combined rates reflect state excise + 6.25% state sales + standard local sales taxes (~10–12%). Municipal cannabis retailer add-ons may vary ±2% by town.
          </p>
        </div>
      </section>
    </div>
  );
}
