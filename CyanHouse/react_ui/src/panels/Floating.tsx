import { ReactNode, RefObject, forwardRef, useImperativeHandle, useLayoutEffect, useRef } from "react";
import { createPortal } from "react-dom";

const GAP = 4, EDGE = 8;

/** A dropdown drawn on the page's body, over everything, lined up with its
 *  button (`anchor`) — so a dialog's scrolling body can't cut it off. Below
 *  the button, or above it when there is more room there; kept inside the
 *  window sideways. Follows the button as anything scrolls or resizes, and
 *  as the button or the box itself changes size (a field growing a row, a
 *  list of choices changing). `className` styles the box itself (its
 *  position is set here, straight on the element, and it stays hidden until
 *  it has one — never drawn where the stylesheet alone would put it). */
export const Floating = forwardRef<HTMLSpanElement, {
  anchor: RefObject<HTMLElement>; className: string; maxHeight?: number; children: ReactNode;
}>(function Floating({ anchor, className, maxHeight = 320, children }, ref) {
  const box = useRef<HTMLSpanElement>(null);
  useImperativeHandle(ref, () => box.current!);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const place = () => {
      const a = anchor.current?.getBoundingClientRect();
      if (!a) return;
      const below = window.innerHeight - a.bottom - GAP - EDGE, above = a.top - GAP - EDGE;
      const down = below >= Math.min(maxHeight, 200) || below >= above;
      const s = el.style;
      s.minWidth = `${a.width}px`;
      s.maxHeight = `${Math.min(maxHeight, down ? below : above)}px`;
      s.left = `${Math.max(EDGE, Math.min(a.left, window.innerWidth - el.offsetWidth - EDGE))}px`;
      s.top = down ? `${a.bottom + GAP}px` : "auto";
      s.bottom = down ? "auto" : `${window.innerHeight - a.top + GAP}px`;
      s.visibility = "visible";
    };
    place();
    const ro = new ResizeObserver(place);
    ro.observe(el);
    if (anchor.current) ro.observe(anchor.current);
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      ro.disconnect();
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [anchor, maxHeight]);
  return createPortal(
    <span ref={box} className={className}
          style={{ position: "fixed", zIndex: 1000, right: "auto", left: 0, top: 0, visibility: "hidden" }}>
      {children}
    </span>,
    document.body);
});
