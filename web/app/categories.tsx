'use client';
import { useEffect, useState, type ReactNode } from 'react';

const KEY = 'terpscout.category';
type Chip = { id: string; label: string; total: number; color: string };

// Below the lg breakpoint the three category columns stack; the chips show one category (or all) at a time. Desktop always shows every column.
export default function CategoryGrid({ chips, children }: { chips: Chip[]; children: ReactNode }) {
  const [active, setActive] = useState('all');
  useEffect(() => { try { const v = localStorage.getItem(KEY); if (v && chips.some((c) => c.id === v)) setActive(v); } catch {} }, [chips]);
  const pick = (id: string) => {
    setActive(id);
    try { localStorage.setItem(KEY, id); } catch {}
  };
  return (
    <>
      <nav aria-label="Category" className="lg:hidden sticky top-0 z-30 -mx-3 px-3 py-2 flex gap-2 overflow-x-auto bg-[#070b0e]/95 backdrop-blur border-b border-slate-800">
        {[{ id: 'all', label: 'All', total: -1, color: '#10b981' }, ...chips].map((c) => (
          <button key={c.id} type="button" aria-pressed={active === c.id} onClick={() => pick(c.id)}
            className={`btn shrink-0 capitalize ${active === c.id ? 'selected' : ''}`}>
            {c.label}{c.total >= 0 && <span className="font-mono opacity-70">{c.total}</span>}
          </button>
        ))}
      </nav>
      <div className="cat-grid grid gap-4 lg:grid-cols-3" data-active={active}>{children}</div>
    </>
  );
}
