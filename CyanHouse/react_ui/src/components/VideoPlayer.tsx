import { useEffect, useRef, useState } from "react";
import { mediaInfo, mediaStreamUrl, mediaSubtitlesUrl } from "../media";

/** Standalone seek-and-play video component. Every scrub of the slider loads
 *  a brand-new stream starting at that timestamp (see api/services/media.py)
 *  rather than seeking within one response, so `displayPosition` is tracked
 *  as `seekOffset + video.currentTime`, not the video element's own clock. */
export interface VideoPlayerProps {
  path: string;
  subtitlesPath?: string;
}

export function VideoPlayer({ path, subtitlesPath }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [duration, setDuration] = useState(0);
  const [seekOffset, setSeekOffset] = useState(0);
  const [displayPosition, setDisplayPosition] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  const loadAt = (seconds: number) => {
    setSeekOffset(seconds);
    setDisplayPosition(seconds);
    const v = videoRef.current;
    if (!v) return;
    v.src = mediaStreamUrl(path, seconds);
    v.load();
    v.play().catch(() => {});
  };

  useEffect(() => {
    let alive = true;
    setError("");
    mediaInfo(path)
      .then((i) => alive && setDuration(i.duration))
      .catch((e) => alive && setError(String(e)));
    loadAt(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  return (
    <div>
      <video
        ref={videoRef}
        controls
        style={{ width: "100%", background: "#000" }}
        onTimeUpdate={(e) => {
          if (!dragging) setDisplayPosition(seekOffset + e.currentTarget.currentTime);
        }}
        onError={() => setError("playback failed — check the backend log")}
      >
        {subtitlesPath && (
          <track kind="subtitles" src={mediaSubtitlesUrl(subtitlesPath)} srcLang="en" label="Subtitles" default />
        )}
      </video>

      <input
        type="range"
        min={0}
        max={duration || 0}
        step={0.1}
        value={displayPosition}
        style={{ width: "100%" }}
        onMouseDown={() => setDragging(true)}
        onChange={(e) => setDisplayPosition(Number(e.target.value))}
        onMouseUp={(e) => {
          setDragging(false);
          loadAt(Number((e.target as HTMLInputElement).value));
        }}
      />
      <div>{formatTime(displayPosition)} / {formatTime(duration)}</div>
      {error && <div style={{ color: "#e5484d" }}>{error}</div>}
    </div>
  );
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}
