import { useEffect, useRef, useState } from "react";
import { useBackToClose } from "../backClose";

export type MenuTab<K extends string> = { key: K; icon: string; label: string };

/** A panel's tabs on a phone, as Media's: one button naming the current
 *  tab, and under it a list of all of them that slides down. A pick, a tap
 *  elsewhere or Back puts it away. */
export function TabMenu<K extends string>({ tabs, value, onChange }: {
  tabs: MenuTab<K>[]; value: K; onChange: (key: K) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useBackToClose(() => setOpen(false), open);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);
  const cur = tabs.find((x) => x.key === value) ?? tabs[0];
  return (
    <div className="tab-menu" ref={box}>
      <button className={"tm-current" + (open ? " open" : "")} aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="tm-icon" aria-hidden>{cur.icon}</span>
        <span className="tm-label">{cur.label}</span>
        <span className="tm-caret" aria-hidden>▾</span>
      </button>
      <div className={"tm-list" + (open ? " open" : "")}>
        {tabs.map((x) => (
          <button key={x.key} className={x.key === value ? "active" : ""}
                  onClick={() => { onChange(x.key); setOpen(false); }}>
            <span className="tm-icon" aria-hidden>{x.icon}</span>
            {x.label}
          </button>
        ))}
      </div>
    </div>
  );
}
