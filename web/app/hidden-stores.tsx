'use client';
import { useEffect, useMemo, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { HIDE_PARAM, HIDE_STORAGE_KEY, parseHidden, serializeHidden } from '@/lib/hidden';

type Store = { id: string; name: string; distance_miles: number };

const readStored = (): string[] => {
  try {
    return parseHidden(localStorage.getItem(HIDE_STORAGE_KEY));
  } catch {
    return [];
  }
};
const writeStored = (ids: string[]) => {
  try {
    if (ids.length) localStorage.setItem(HIDE_STORAGE_KEY, serializeHidden(ids));
    else localStorage.removeItem(HIDE_STORAGE_KEY);
  } catch {}
};

export default function HiddenStores({ stores, hidden }: { stores: Store[]; hidden: string[] }) {
  const router = useRouter();
  const sp = useSearchParams();
  const [, startTransition] = useTransition();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const urlValue = sp.get(HIDE_PARAM) ?? '';

  const apply = (ids: string[]) => {
    writeStored(ids);
    const u = new URLSearchParams(sp.toString());
    const v = serializeHidden(ids);
    if (v) u.set(HIDE_PARAM, v);
    else u.delete(HIDE_PARAM);
    ['p_concentrate', 'p_flower', 'p_vapes'].forEach((k) => u.delete(k));
    startTransition(() => router.replace(`/?${u.toString()}`));
  };

  // Restore the saved choice when the URL doesn't carry it (fresh visit, or a link that dropped the param).
  useEffect(() => {
    const stored = readStored();
    if (serializeHidden(stored) === serializeHidden(parseHidden(urlValue))) return;
    if (urlValue === '' && stored.length) {
      const u = new URLSearchParams(sp.toString());
      u.set(HIDE_PARAM, serializeHidden(stored));
      startTransition(() => router.replace(`/?${u.toString()}`));
    } else if (urlValue) {
      writeStored(parseHidden(urlValue)); // a shared link's choice becomes this browser's choice
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlValue]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const hiddenSet = useMemo(() => new Set(hidden), [hidden]);
  const hiddenHere = stores.filter((s) => hiddenSet.has(s.id)).length;
  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return f ? stores.filter((s) => s.name.toLowerCase().includes(f)) : stores;
  }, [stores, filter]);

  const toggle = (id: string) =>
    apply(hiddenSet.has(id) ? hidden.filter((x) => x !== id) : [...hidden, id]);

  if (stores.length === 0 && hidden.length === 0) return null;

  return (
    <>
      <div className="flex items-center justify-between gap-2 px-1">
        <button type="button" className="btn !py-1.5 !px-3 text-xs" onClick={() => setOpen(true)}>
          🏪 Dispensaries in this area ({stores.length})
          {hiddenHere > 0 && <span className="ml-1.5 badge text-rose-300 border-rose-500/40">{hiddenHere} hidden</span>}
        </button>
        {hidden.length > 0 && (
          <button type="button" className="text-xs text-slate-400 hover:text-emerald-300 px-2 py-1" onClick={() => apply([])}>
            Show all
          </button>
        )}
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/75 backdrop-blur-sm p-0 sm:p-4"
          onClick={(e) => e.target === e.currentTarget && setOpen(false)}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-label="Choose dispensaries to hide"
            className="glass-card w-full sm:max-w-xl rounded-t-3xl sm:rounded-2xl p-5 space-y-3 max-h-[90dvh] overflow-y-auto border-t sm:border border-emerald-500/30"
          >
            <div className="w-10 h-1 bg-slate-700/80 rounded-full mx-auto sm:hidden" aria-hidden="true" />
            <div className="flex items-start justify-between gap-3 border-b border-slate-800/80 pb-3">
              <div>
                <h2 className="text-base font-extrabold text-white">Dispensaries in this area</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Uncheck a dispensary to leave its deals out. Saved on this device.
                </p>
              </div>
              <button type="button" className="btn !py-1 !px-2.5 text-slate-300" aria-label="Close" onClick={() => setOpen(false)}>
                ✕
              </button>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="search"
                aria-label="Filter dispensaries by name"
                placeholder="Filter by name…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="flex-1 min-w-0 !py-2"
              />
              <button
                type="button"
                className="btn !py-1.5 !px-2.5 text-xs whitespace-nowrap"
                onClick={() => apply([...new Set([...hidden, ...stores.map((s) => s.id)])])}
              >
                Hide all
              </button>
              <button type="button" className="btn !py-1.5 !px-2.5 text-xs whitespace-nowrap" onClick={() => apply(hidden.filter((id) => !stores.some((s) => s.id === id)))}>
                Show all
              </button>
            </div>

            <ul className="divide-y divide-slate-800/80 rounded-xl border border-slate-800/80 bg-slate-950/40">
              {shown.length === 0 && <li className="p-4 text-center text-xs text-slate-500">No dispensaries match.</li>}
              {shown.map((s) => {
                const isHidden = hiddenSet.has(s.id);
                return (
                  <li key={s.id}>
                    <label className="flex items-center gap-3 px-3 py-3 min-h-[48px] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={!isHidden}
                        onChange={() => toggle(s.id)}
                        className="h-5 w-5 shrink-0 accent-emerald-500"
                      />
                      <span className={`flex-1 min-w-0 text-sm break-words ${isHidden ? 'text-slate-500 line-through' : 'text-slate-100'}`}>
                        {s.name}
                      </span>
                      <span className="text-[11px] font-mono text-slate-400 shrink-0">{s.distance_miles} mi</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
      )}
    </>
  );
}
