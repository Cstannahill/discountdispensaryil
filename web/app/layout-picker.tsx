'use client';
import { useRouter } from 'next/navigation';
import { useTransition } from 'react';
import { LAYOUTS, LAYOUT_COOKIE, type LayoutId } from '@/lib/layouts';

// The "Layout" group inside the ⋯ menu. Writes the cookie the server reads, then re-renders the page.
export default function LayoutPicker({ current, onPicked }: { current: LayoutId; onPicked?: () => void }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const pick = (id: LayoutId) => {
    document.cookie = `${LAYOUT_COOKIE}=${id}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
    window.dispatchEvent(new CustomEvent('terpscout:pending', { detail: { source: 'layout', pending: true } }));
    startTransition(() => {
      router.refresh();
      onPicked?.();
    });
    // The refresh swaps the whole page; clear the spinner shortly after it lands.
    setTimeout(() => window.dispatchEvent(new CustomEvent('terpscout:pending', { detail: { source: 'layout', pending: false } })), 1200);
  };

  return (
    <div role="group" aria-label="Page layout" className="pt-1 mt-1 border-t border-slate-800/80">
      <p className="px-3 pt-1.5 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">Layout</p>
      {LAYOUTS.map((l) => {
        const selected = l.id === current;
        return (
          <button
            key={l.id}
            type="button"
            role="menuitemradio"
            aria-checked={selected}
            disabled={isPending}
            onClick={() => (selected ? onPicked?.() : pick(l.id))}
            className={`w-full flex items-center gap-2 rounded-xl px-3 py-2 text-left text-sm hover:bg-slate-800/80 ${
              selected ? 'text-emerald-300 font-bold' : 'text-slate-200'
            }`}
          >
            <span aria-hidden="true" className="w-4 text-center text-xs">{selected ? '●' : '○'}</span>
            <span className="flex-1 min-w-0">
              <span className="block leading-tight">{l.label}</span>
              <span className="block text-[10px] font-normal text-slate-400 leading-tight">{l.hint}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
