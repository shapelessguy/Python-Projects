import { useEffect, useRef, useState } from "react";

/** A player's volume on a phone (films, music): a speaker button, and
 *  over it a small upright slider while open -- in the player's row and in
 *  full screen alike. A tap anywhere else puts it away. `onUse` keeps the full-screen
 *  controls from fading while it is being used. */
export function VolumePop({ value, onChange, title, onUse }: {
  value: number; onChange: (v: number) => void; title: string; onUse?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);
  return (
    <span className="mv-volpop" ref={box}>
      <button className={"ghost" + (open ? " active" : "")} title={title} aria-label={title}
              onClick={() => { setOpen(!open); onUse?.(); }}>
        <span aria-hidden>{value === 0 ? "🔇" : "🔊"}</span>
      </button>
      {open && (
        <span className="mv-volpanel" onPointerDown={onUse} onPointerMove={onUse}>
          <input type="range" min={0} max={1} step={0.01} value={value} aria-label={title}
                 onChange={(e) => { onChange(+e.target.value); onUse?.(); }} />
        </span>
      )}
    </span>
  );
}
