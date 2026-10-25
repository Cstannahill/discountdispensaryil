export interface RelativeTimeInfo {
  label: string;
  full: string;
  isLive: boolean;
}

export function formatRelativeTime(isoString: string, nowMs = Date.now()): RelativeTimeInfo {
  const t = Date.parse(isoString);
  if (Number.isNaN(t)) {
    return {
      label: 'Recently observed',
      full: 'Observation timestamp unavailable',
      isLive: false,
    };
  }

  const full = new Date(t).toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    dateStyle: 'short',
    timeStyle: 'short',
  });

  const diffMs = nowMs - t;
  // If in the future or under 1 minute
  if (diffMs < 60_000) {
    return { label: 'Just now', full, isLive: true };
  }

  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 60) {
    return { label: `${diffMins}m ago`, full, isLive: true };
  }

  const diffHours = Math.floor(diffMs / 3_600_000);
  if (diffHours < 24) {
    return { label: `${diffHours}h ago`, full, isLive: diffHours < 4 };
  }

  const diffDays = Math.floor(diffMs / 86_400_000);
  return { label: `${diffDays}d ago`, full, isLive: false };
}
