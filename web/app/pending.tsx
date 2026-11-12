'use client';
import { useEffect, useState } from 'react';

// Listens for 'terpscout:pending' events from the location and filter controls and shows a spinner
// and marks <html data-pending="1"> so the results can dim (see globals.css) while listings reload.
export default function PendingBar() {
  const [on, setOn] = useState(false);

  useEffect(() => {
    const active = new Set<string>();
    let failsafe: ReturnType<typeof setTimeout> | undefined;
    const apply = () => {
      const pending = active.size > 0;
      setOn(pending);
      document.documentElement.dataset.pending = pending ? '1' : '';
      clearTimeout(failsafe);
      if (pending) failsafe = setTimeout(() => { active.clear(); apply(); }, 20000);
    };
    const handler = (e: Event) => {
      const d = (e as CustomEvent<{ source: string; pending: boolean }>).detail;
      if (!d) return;
      if (d.pending) active.add(d.source); else active.delete(d.source);
      apply();
    };
    window.addEventListener('terpscout:pending', handler);
    return () => {
      window.removeEventListener('terpscout:pending', handler);
      clearTimeout(failsafe);
      document.documentElement.dataset.pending = '';
    };
  }, []);

  if (!on) return null;
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 top-20 z-[60] flex justify-center">
      <div className="flex items-center gap-2 rounded-full border border-emerald-500/40 bg-slate-950/95 px-3.5 py-2 shadow-lg shadow-black/50">
        <span className="pending-spinner h-4 w-4 rounded-full border-2 border-emerald-400/30 border-t-emerald-400" aria-hidden="true" />
        <span className="text-xs font-semibold text-emerald-300">Updating deals…</span>
      </div>
    </div>
  );
}
