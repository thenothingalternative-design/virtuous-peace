/**
 * Shared utility functions used across screens.
 */

/** Format seconds as human-readable duration. Matches desktop fmt_dur exactly. */
export function fmtDuration(seconds: number): string {
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${String(m).padStart(2, '0')}m`;
  }
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

/** Format elapsed seconds as MM:SS (used in timer displays). */
export function fmtElapsed(seconds: number): string {
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${String(m).padStart(2, '0')}m`;
  }
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/** Format an ISO timestamp for display. */
export function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month:  'short',
      day:    'numeric',
      hour:   '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

/** Count occurrences of items in an array. Returns sorted [name, count] pairs. */
export function countItems(items: string[]): [string, number][] {
  const counts: Record<string, number> = {};
  for (const item of items) {
    counts[item] = (counts[item] ?? 0) + 1;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1]);
}

/**
 * Strip protocol/www from a URL string so "https://www.youtube.com/watch?v=x"
 * becomes "youtube.com" for display and matching.
 */
export function cleanUrl(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/https?:\/\//, '')
    .replace(/^www\./, '')
    .split('/')[0]
    .trim();
}

/** Days remaining from an ISO timestamp. Returns 0 if in the past. */
export function daysUntil(isoTimestamp: string): number {
  try {
    const ends = new Date(isoTimestamp).getTime();
    return Math.max(0, Math.ceil((ends - Date.now()) / 86_400_000));
  } catch {
    return 0;
  }
}
