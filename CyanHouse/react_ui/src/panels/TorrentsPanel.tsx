import { useEffect, useState } from "react";
import { api, Torrent, TorrentVideo } from "../api";
import { VideoPlayer } from "../components/VideoPlayer";

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

  const [expanded, setExpanded] = useState<string | null>(null);
  const [videos, setVideos] = useState<TorrentVideo[] | null>(null);
  const [videosError, setVideosError] = useState("");
  const [playing, setPlaying] = useState<TorrentVideo | null>(null);

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

  const toggleExpand = (hash: string) => {
    if (expanded === hash) {
      setExpanded(null);
      return;
    }
    setExpanded(hash);
    setVideos(null);
    setVideosError("");
    setPlaying(null);
    api
      .torrentVideos(hash)
      .then(setVideos)
      .catch((e) => setVideosError(String(e.message ?? e)));
  };

  return (
    <div className="torrents">
      <h2>Torrents</h2>
      {error && <p className="error">{error}</p>}
      {!error && torrents && torrents.length === 0 && (
        <p className="muted">No torrents.</p>
      )}
      {torrents && torrents.length > 0 && (
        <div className="torrent-list">
          {torrents.map((t) => (
            <div className="torrent-row" key={t.hash}>
              <div className="torrent-top" onClick={() => toggleExpand(t.hash)} style={{ cursor: "pointer" }}>
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

              {expanded === t.hash && (
                <div className="torrent-videos">
                  {videosError && <p className="error">{videosError}</p>}
                  {!videosError && videos === null && <p className="muted">Loading files…</p>}
                  {videos !== null && videos.length === 0 && (
                    <p className="muted">No video files found.</p>
                  )}
                  {videos !== null && videos.length > 0 && (
                    <ul>
                      {videos.map((v) => (
                        <li key={v.path}>
                          <button className="ghost" onClick={() => setPlaying(v)}>
                            ▶ {v.name} ({bytes(v.size)})
                            {v.subtitlePath && " · subs found"}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {playing && (
                    <VideoPlayer
                      path={playing.path}
                      subtitlesPath={playing.subtitlePath ?? undefined}
                    />
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
