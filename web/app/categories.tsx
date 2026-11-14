'use client';
import { useEffect, useState, type ReactNode } from 'react';

export const CATEGORY_EVENT = 'terpscout:category-change';
export const CATEGORY_STORAGE_KEY = 'terpscout.category';

export type CategoryChip = { id: string; label: string; total: number; color: string };

// Below the lg breakpoint the category columns stack; the active category (defaulting to flower)
// or all at a time is displayed based on data-active. Desktop always shows every column.
export default function CategoryGrid({
  chips,
  children,
  className = 'grid gap-4 lg:grid-cols-2 items-start',
  solo = false,
}: {
  chips?: readonly CategoryChip[];
  children: ReactNode;
  /** Grid classes for the category sections; the default is the classic two-column layout. */
  className?: string;
  /** Show only the active category at every width (classic does so only below lg). */
  solo?: boolean;
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
    <div className={`cat-grid ${solo ? 'cat-solo ' : ''}${className}`} data-active={active}>
      {children}
    </div>
  );
}
