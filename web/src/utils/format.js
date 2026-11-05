/**
 * Formatting helpers for byte sizes, download speeds, context lengths, and TTLs.
 */

export function formatBytes(bytes) {
  const num = Number(bytes || 0);
  if (!Number.isFinite(num) || num <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let idx = 0;
  let val = num;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx += 1;
  }
  return `${val >= 100 || idx === 0 ? val.toFixed(0) : val.toFixed(2)} ${units[idx]}`;
}

export function formatSpeed(bytesPerSec) {
  const num = Number(bytesPerSec || 0);
  if (!Number.isFinite(num) || num <= 0) return '';
  return `${formatBytes(num)}/s`;
}

export function formatContextTokens(tokens) {
  const num = Number(tokens || 0);
  if (!Number.isFinite(num) || num <= 0) return '-';
  if (num >= 1024 && num % 1024 === 0) {
    return `${num / 1024}K`;
  }
  return num.toLocaleString();
}

export function formatDurationSeconds(seconds) {
  const sec = Math.max(0, Math.floor(Number(seconds || 0)));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return remM > 0 ? `${h}h ${remM}m` : `${h}h`;
}

export function formatIsoShort(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return String(isoStr);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (e) {
    return String(isoStr);
  }
}
