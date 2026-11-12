'use client';
import { useEffect, useState } from 'react';

// Listens for 'terpscout:pending' events from the location and filter controls and shows a top progress bar,
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
    <div role="status" aria-live="polite" className="fixed inset-x-0 top-0 z-[60]">
      <span className="sr-only">Updating deals</span>
      <div className="pending-bar h-1 w-full overflow-hidden bg-emerald-950/60">
        <div className="pending-bar-fill h-full w-1/3 bg-emerald-400" />
      </div>
      <p className="mx-auto mt-2 w-fit rounded-full border border-emerald-500/40 bg-slate-950/95 px-3 py-1 text-[11px] font-semibold text-emerald-300 shadow-lg">
        Updating deals…
      </p>
    </div>
  );
}
