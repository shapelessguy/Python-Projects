import { useEffect, useState } from "react";
import { api, Torrent } from "../api";

const POLL_MS = 3000;

function bytes(n: number): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function speed(n: number): string {
  return n > 0 ? `${bytes(n)}/s` : "–";
}

function eta(seconds: number): string {
  if (seconds <= 0 || seconds >= 8640000) return "–";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

const STATE_LABEL: Record<string, string> = {
  downloading: "Downloading",
  stalledDL: "Stalled",
  metaDL: "Fetching metadata",
  pausedDL: "Paused",
  queuedDL: "Queued",
  checkingDL: "Checking",
  forcedDL: "Downloading",
  uploading: "Seeding",
  stalledUP: "Seeding (idle)",
  pausedUP: "Completed",
  queuedUP: "Queued (seed)",
  checkingUP: "Checking",
  forcedUP: "Seeding",
  error: "Error",
  missingFiles: "Missing files",
};

export function TorrentsPanel() {
  const [torrents, setTorrents] = useState<Torrent[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const tick = () =>
      api
        .torrents()
        .then((t) => {
          if (alive) {
            setTorrents(t);
            setError("");
          }
        })
        .catch((e) => {
          if (alive) setError(String(e.message ?? e));
        });
    tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="torrents">
      <h2>Torrents</h2>
      {error && <p className="error">{error}</p>}
      {!error && torrents && torrents.length === 0 && (
        <p className="muted">No torrents.</p>
      )}
      {torrents && torrents.length > 0 && (
        <div className="torrent-list">
          {torrents.map((t, i) => (
            <div className="torrent-row" key={i}>
              <div className="torrent-top">
                <span className="torrent-name" title={t.name}>{t.name}</span>
                <span className="torrent-state">{STATE_LABEL[t.state] ?? t.state}</span>
              </div>
              <div className="torrent-bar">
                <div
                  className="torrent-bar-fill"
                  style={{ width: `${Math.round(t.progress * 100)}%` }}
                />
              </div>
              <div className="torrent-meta">
                <span>{Math.round(t.progress * 100)}%</span>
                <span>{bytes(t.size)}</span>
                <span>↓ {speed(t.dlspeed)}</span>
                <span>↑ {speed(t.upspeed)}</span>
                <span>ETA {eta(t.eta)}</span>
                <span>Ratio {t.ratio.toFixed(2)}</span>
                <span>{t.num_seeds} seeds / {t.num_leechs} peers</span>
                {t.category && <span className="muted">{t.category}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
