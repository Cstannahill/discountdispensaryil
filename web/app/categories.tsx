'use client';
import { useEffect, useState, type ReactNode } from 'react';

export const CATEGORY_EVENT = 'terpscout:category-change';
export const CATEGORY_STORAGE_KEY = 'terpscout.category';

export type CategoryChip = { id: string; label: string; total: number; color: string };

// Below the lg breakpoint the three category columns stack; the active category (defaulting to flower)
// or all at a time is displayed based on data-active. Desktop always shows every column.
export default function CategoryGrid({
  chips,
  children,
}: {
  chips?: readonly CategoryChip[];
  children: ReactNode;
}) {
  const [active, setActive] = useState('flower');

  useEffect(() => {
    try {
      const v = localStorage.getItem(CATEGORY_STORAGE_KEY);
      if (v) setActive(v);
    } catch {}

    const onCategoryChange = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail) setActive(detail);
    };

    window.addEventListener(CATEGORY_EVENT, onCategoryChange);
    return () => window.removeEventListener(CATEGORY_EVENT, onCategoryChange);
  }, []);

  return (
    <div className="cat-grid grid gap-4 lg:grid-cols-3 items-start" data-active={active}>
      {children}
    </div>
  );
}
