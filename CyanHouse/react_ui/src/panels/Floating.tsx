import { CSSProperties, ReactNode, RefObject, forwardRef, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";

const GAP = 4, EDGE = 8;

/** A dropdown drawn on the page's body, over everything, lined up with its
 *  button (`anchor`) — so a dialog's scrolling body can't cut it off. Below
 *  the button, or above it when there is more room there; kept inside the
 *  window sideways. Follows the button as anything scrolls or resizes.
 *  `className` styles the box itself (its position is set here). */
export const Floating = forwardRef<HTMLSpanElement, {
  anchor: RefObject<HTMLElement>; className: string; maxHeight?: number; children: ReactNode;
}>(function Floating({ anchor, className, maxHeight = 320, children }, ref) {
  const [style, setStyle] = useState<CSSProperties>({ position: "fixed", visibility: "hidden" });
  useLayoutEffect(() => {
    const place = () => {
      const a = anchor.current?.getBoundingClientRect();
      if (!a) return;
      const below = window.innerHeight - a.bottom - GAP - EDGE, above = a.top - GAP - EDGE;
      const down = below >= Math.min(maxHeight, 200) || below >= above;
      const box = typeof ref === "object" && ref?.current;
      const width = box ? box.offsetWidth : a.width;
      setStyle({
        position: "fixed", zIndex: 1000, right: "auto",
        left: Math.max(EDGE, Math.min(a.left, window.innerWidth - width - EDGE)),
        top: down ? a.bottom + GAP : "auto",
        bottom: down ? "auto" : window.innerHeight - a.top + GAP,
        minWidth: a.width,
        maxHeight: Math.min(maxHeight, down ? below : above),
      });
    };
    place();
    // Once more after the box has its width, to keep it inside the window.
    const frame = requestAnimationFrame(place);
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [anchor, ref, maxHeight]);
  return createPortal(<span ref={ref} className={className} style={style}>{children}</span>, document.body);
});
