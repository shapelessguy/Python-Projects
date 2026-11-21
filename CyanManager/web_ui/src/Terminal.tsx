import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "./api";

type Line = { seq: number; text: string };
const KEEP = 1000;

/** What CyanManager printed: the last lines it keeps, then new ones as they come. */
export function Terminal({ onClose }: { onClose: () => void }) {
  const [lines, setLines] = useState<Line[]>([]);
  const next = useRef(0);
  const box = useRef<HTMLPreElement>(null);
  const atBottom = useRef(true);

  useEffect(() => {
    let stop = false;
    const pull = async () => {
      try {
        const d = await api<{ next: number; lines: Line[] }>("GET", `/api/logs?after=${next.current}`);
        if (stop) return;
        next.current = d.next;
        if (d.lines.length) setLines((l) => [...l, ...d.lines].slice(-KEEP));
      } catch {
        /* CyanManager restarting: the next pull tries again */
      }
    };
    pull();
    const id = window.setInterval(pull, 1000);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => {
      stop = true;
      window.clearInterval(id);
      window.removeEventListener("keydown", esc);
    };
  }, [onClose]);

  // Follow the end only if the view was already there
  useLayoutEffect(() => {
    const el = box.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="terminal">
        <div className="terminal-head">
          <strong>Terminal</strong>
          <div className="spacer" />
          <button className="btn small" onClick={() => setLines([])}>Clear</button>
          <button className="btn small" onClick={onClose}>Close</button>
        </div>
        <pre
          ref={box}
          onScroll={(e) => {
            const el = e.currentTarget;
            atBottom.current = el.scrollTop >= el.scrollHeight - el.clientHeight - 4;
          }}
        >
          {lines.map((l) => l.text).join("\n")}
        </pre>
      </div>
    </div>
  );
}
