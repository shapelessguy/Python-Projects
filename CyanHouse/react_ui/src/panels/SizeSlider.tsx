import { ReactNode, useEffect, useRef, useState } from "react";
import { usePhone } from "../narrow";

type Props = {
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
  title: string;
  className?: string;
  /** The phone button's face; resize arrows when not given. */
  icon?: ReactNode;
};

/** A card/cover size slider (or any other slider that is too wide for a
 *  phone's toolbar, like the player's volume). On a phone it is only a button --
 *  the slider is too wide to sit in a toolbar there -- and tapping it opens
 *  the slider in a popover, closed again by letting go of the slider or
 *  tapping anywhere else. */
export function SizeSlider({ min, max, step, value, onChange, title, className, icon }: Props) {
  const narrow = usePhone();
  // Where the popover goes: just below the button, as a strip across the
  // screen -- the button sits at the left in one toolbar and the right in
  // another, and an anchored popover would run off one edge or the other.
  const [openTop, setOpenTop] = useState<number | null>(null);
  const open = openTop !== null;
  const setOpen = (o: boolean) =>
    setOpenTop(o && boxRef.current ? boxRef.current.getBoundingClientRect().bottom + 6 : null);
  const boxRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  const range = (
    <input className={narrow ? "size-pop-range" : className} type="range"
           min={min} max={max} step={step} value={value} title={title}
           onChange={(e) => onChange(+e.target.value)}
           // Let go of the slider once set, so the arrow keys go back to
           // whatever they did before (turning pages) rather than nudging
           // the size -- and on a phone, put the popover away.
           onPointerUp={(e) => { e.currentTarget.blur(); if (narrow) setOpen(false); }} />
  );
  if (!narrow) return range;

  return (
    <span className="size-pop" ref={boxRef}>
      <button className={"ghost size-pop-btn" + (open ? " active" : "")} title={title} aria-label={title}
              onClick={() => setOpen(!open)}>
        {/* by default arrows out to the corners -- not a magnifier, which is search */}
        {icon ?? (
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 10V4h6M20 14v6h-6M4 4l6.5 6.5M20 20l-6.5-6.5" />
          </svg>
        )}
      </button>
      {open && <span className="size-pop-panel" style={{ top: openTop }}>{range}</span>}
    </span>
  );
}
