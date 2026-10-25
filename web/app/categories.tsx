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
