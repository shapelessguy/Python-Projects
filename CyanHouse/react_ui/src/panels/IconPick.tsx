import { ReactNode, useEffect, useRef, useState } from "react";
import { useBackToClose } from "../backClose";

export type IconChoice = { key: string; icon: ReactNode; label: string };

/** One of a few choices (a panel's views) behind a single button showing
 *  the current one's icon; tapped, a small list of them all opens under
 *  it, icon and name. A pick, a tap elsewhere or Back puts it away. */
export function IconPick({ choices, value, onChange }: {
  choices: IconChoice[]; value: string; onChange: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useBackToClose(() => setOpen(false), open);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);
  const cur = choices.find((c) => c.key === value) ?? choices[0];
  if (!cur) return null;
  return (
    <span className="icon-pick" ref={box}>
      <button className={"ghost" + (open ? " active" : "")} title={cur.label} aria-label={cur.label}
              aria-expanded={open} onClick={() => setOpen(!open)}>
        {cur.icon}
      </button>
      {open && (
        <span className="ip-list">
          {choices.map((c) => (
            <button key={c.key} className={c.key === value ? "active" : ""}
                    onClick={() => { onChange(c.key); setOpen(false); }}>
              <span className="ip-icon" aria-hidden>{c.icon}</span>
              {c.label}
            </button>
          ))}
        </span>
      )}
    </span>
  );
}

