'use client';
import { useEffect, useState, type ReactNode } from 'react';
import { CATEGORY_EVENT, CATEGORY_STORAGE_KEY, type CategoryChip } from './categories';

const ICONS: Record<string, string> = { flower: '🌿', concentrate: '🍯', vapes: '💨', edibles: '🍬', all: '⚡' };

function pickCategory(id: string) {
  try {
    localStorage.setItem(CATEGORY_STORAGE_KEY, id);
  } catch {}
  window.dispatchEvent(new CustomEvent(CATEGORY_EVENT, { detail: id }));
}

export function useActiveCategory() {
  const [active, setActive] = useState('flower');
  useEffect(() => {
    try {
      const v = localStorage.getItem(CATEGORY_STORAGE_KEY);
      if (v) setActive(v);
    } catch {}
    const on = (e: Event) => {
      const d = (e as CustomEvent<string>).detail;
      if (d) setActive(d);
    };
    window.addEventListener(CATEGORY_EVENT, on);
    return () => window.removeEventListener(CATEGORY_EVENT, on);
  }, []);
  return active;
}

// Category switcher for the non-classic layouts. Shares the classic layout's event and storage key, so the
// chosen category carries over when a visitor changes layout.
export default function CategoryTabs({
  chips,
  includeAll = false,
  variant = 'tabs',
  className = '',
}: {
  chips: readonly CategoryChip[];
  includeAll?: boolean;
  variant?: 'tabs' | 'pills';
  className?: string;
}) {
  const active = useActiveCategory();
  const ordered = [
    ...chips.filter((c) => c.id === 'flower'),
    ...chips.filter((c) => c.id !== 'flower'),
    ...(includeAll ? [{ id: 'all', label: 'All', total: chips.reduce((n, c) => n + c.total, 0), color: '#10b981' }] : []),
  ];
  // "All" is only offered by some layouts; fall back to flower where it is not.
  const current = ordered.some((c) => c.id === active) ? active : 'flower';
  useEffect(() => {
    if (current !== active) pickCategory(current);
  }, [current, active]);

  return (
    <nav
      aria-label="Category navigation"
      className={`flex items-center overflow-x-auto no-scrollbar ${variant === 'tabs' ? 'border-b border-slate-800/80' : 'gap-2'} ${className}`}
    >
      {ordered.map((c) => {
        const on = current === c.id;
        return variant === 'tabs' ? (
          <button
            key={c.id}
            type="button"
            aria-pressed={on}
            onClick={() => pickCategory(c.id)}
            style={on ? { borderColor: c.color } : undefined}
            className={`shrink-0 capitalize px-3 py-2.5 text-[13px] font-bold border-b-2 -mb-px transition-colors ${
              on ? 'text-white' : 'text-slate-400 border-transparent hover:text-slate-200'
            }`}
          >
            {c.label}
            <span className="ml-1.5 font-mono text-[10px] font-medium text-slate-500">{c.total}</span>
          </button>
        ) : (
          <button
            key={c.id}
            type="button"
            aria-pressed={on}
            onClick={() => pickCategory(c.id)}
            className={`shrink-0 capitalize rounded-full border px-3.5 py-2 text-[13px] font-bold transition-colors ${
              on
                ? 'bg-slate-100 text-slate-950 border-slate-100'
                : 'bg-slate-950 text-slate-300 border-slate-700/80 hover:border-slate-500'
            }`}
          >
            <span aria-hidden="true">{ICONS[c.id] ?? '🌿'}</span> {c.label}
            <span className="ml-1.5 text-[11px] font-semibold opacity-60">{c.total}</span>
          </button>
        );
      })}
    </nav>
  );
}

// A tile that switches to its category and scrolls to the listings (overview layout).
export function CategoryJump({ id, className, style, children }: { id: string; className?: string; style?: React.CSSProperties; children: ReactNode }) {
  return (
    <button
      type="button"
      className={className}
      style={style}
      onClick={() => {
        pickCategory(id);
        document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }}
    >
      {children}
    </button>
  );
}
