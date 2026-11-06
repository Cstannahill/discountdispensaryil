// Dispensaries a user chose to ignore. Kept in localStorage and mirrored into the `hide` query param so the server can filter.
export const HIDE_PARAM = 'hide';
export const HIDE_STORAGE_KEY = 'terpscout.hidden-stores';
const MAX_HIDDEN = 100;
const ID_RE = /^[A-Za-z0-9_.:-]{1,64}$/;

/** Parses a comma-separated id list: drops malformed ids and duplicates, caps the count. */
export function parseHidden(v?: string | null): string[] {
  if (!v) return [];
  const out: string[] = [];
  for (const raw of v.split(',')) {
    const id = raw.trim();
    if (ID_RE.test(id) && !out.includes(id)) out.push(id);
    if (out.length >= MAX_HIDDEN) break;
  }
  return out;
}

export const serializeHidden = (ids: readonly string[]) => parseHidden(ids.join(',')).join(',');
