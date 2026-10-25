'use client';
import { useEffect, useState } from 'react';

const TOAST_EVENT = 'terpscout:toast';

export function showToast(message: string) {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(TOAST_EVENT, { detail: message }));
  }
}

export default function ToastContainer() {
  const [msg, setMsg] = useState('');
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    const handler = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (text) {
        setMsg(text);
        setVisible(true);
        clearTimeout(timer);
        timer = setTimeout(() => {
          setVisible(false);
        }, 2500);
      }
    };

    window.addEventListener(TOAST_EVENT, handler);
    return () => {
      window.removeEventListener(TOAST_EVENT, handler);
      clearTimeout(timer);
    };
  }, []);

  if (!visible || !msg) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 pointer-events-none transition-all duration-200 ease-out"
    >
      <div className="glass-card px-4 py-2.5 rounded-full border border-emerald-400/60 shadow-xl shadow-black/80 flex items-center gap-2 text-xs font-semibold text-emerald-300 max-w-[90vw] text-center">
        <span aria-hidden="true">✨</span>
        <span>{msg}</span>
      </div>
    </div>
  );
}
