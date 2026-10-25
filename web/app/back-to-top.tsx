'use client';
import { useEffect, useState } from 'react';

export default function BackToTop() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setVisible(window.scrollY > 400);
    };
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  if (!visible) return null;

  return (
    <button
      type="button"
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      aria-label="Back to top"
      className="fixed bottom-5 right-5 z-40 flex items-center gap-1.5 rounded-full bg-slate-900/90 hover:bg-slate-800/95 border border-slate-700/80 hover:border-emerald-500/50 text-slate-200 hover:text-emerald-300 shadow-xl backdrop-blur-md px-3.5 py-2 font-mono text-xs transition-all duration-200 cursor-pointer"
    >
      <span className="text-emerald-400 font-bold" aria-hidden="true">↑</span>
      <span className="font-semibold tracking-wide">Top</span>
    </button>
  );
}
