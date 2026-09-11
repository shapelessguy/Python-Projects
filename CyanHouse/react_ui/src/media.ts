// Self-contained media-playback API — mirrors api/routers/media.py 1:1. No
// dependency on anything else in the app (not even api.ts), so this stays a
// standalone piece usable from wherever ends up calling it.

export function mediaStreamUrl(path: string, start: number): string {
  return `/api/media/stream?path=${encodeURIComponent(path)}&start=${start}`;
}

export function mediaSubtitlesUrl(path: string): string {
  return `/api/media/subtitles?path=${encodeURIComponent(path)}`;
}

export async function mediaInfo(path: string): Promise<{ duration: number }> {
  const r = await fetch(`/api/media/info?path=${encodeURIComponent(path)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}
