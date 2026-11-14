'use client';
import { useEffect, useState } from 'react';
import { openCalculator } from './calculator';
import { openSavedDeals, getSavedDeals, SAVED_EVENT } from './saved-modal';

// Navigation for the "app" layout: a bottom tab bar on phones, a side rail from lg up.
export default function AppNav() {
  const [saved, setSaved] = useState(0);
  useEffect(() => {
    const on = () => setSaved(getSavedDeals().length);
    on();
    window.addEventListener(SAVED_EVENT, on);
    return () => window.removeEventListener(SAVED_EVENT, on);
  }, []);

  const items: { label: string; icon: string; badge?: number; current?: boolean; run: () => void }[] = [
    { label: 'Deals', icon: '🏷️', current: true, run: () => window.scrollTo({ top: 0, behavior: 'smooth' }) },
    {
      label: 'Search',
      icon: '🔍',
      run: () => {
        const el = document.querySelector<HTMLInputElement>('input[type="search"]');
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el?.focus({ preventScroll: true });
      },
    },
    { label: 'Saved', icon: '⭐', badge: saved, run: () => openSavedDeals() },
    { label: 'Calculator', icon: '🧮', run: () => openCalculator() },
  ];

  return (
    <nav
      aria-label="App navigation"
      className="fixed bottom-0 inset-x-0 z-40 flex border-t border-slate-800 bg-slate-950/95 backdrop-blur px-1.5 pt-1.5 pb-[max(0.5rem,env(safe-area-inset-bottom))] lg:static lg:z-auto lg:w-48 lg:shrink-0 lg:flex-col lg:gap-1 lg:self-start lg:sticky lg:top-4 lg:rounded-2xl lg:border lg:p-2"
    >
      {items.map((it) => (
        <button
          key={it.label}
          type="button"
          onClick={it.run}
          aria-current={it.current ? 'page' : undefined}
          className={`relative flex-1 flex flex-col items-center gap-0.5 rounded-xl py-1 text-[10px] font-bold lg:flex-none lg:flex-row lg:gap-2.5 lg:px-3 lg:py-2.5 lg:text-sm ${
            it.current ? 'text-emerald-400 lg:bg-emerald-500/15' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <span aria-hidden="true" className={`text-lg leading-none lg:text-base ${it.current ? '' : 'grayscale opacity-70'}`}>{it.icon}</span>
          <span>{it.label}</span>
          {it.badge ? (
            <span className="absolute top-0 right-[calc(50%-1.4rem)] lg:static lg:ml-auto min-w-4 h-4 px-1 rounded-full bg-emerald-500 text-slate-950 text-[9px] font-extrabold flex items-center justify-center">
              {it.badge}
            </span>
          ) : null}
        </button>
      ))}
    </nav>
  );
}
