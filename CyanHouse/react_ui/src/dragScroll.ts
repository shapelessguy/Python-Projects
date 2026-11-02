import { RefObject, useEffect } from "react";

/** Lets a sideways-scrolling strip be moved without a touch screen: the
 *  mouse wheel scrolls it sideways, and dragging it with the mouse slides it
 *  (a drag that moved isn't also a click on whatever it started on). Touch
 *  needs none of this -- it swipes an overflow-x box natively. */
export function useDragScroll(ref: RefObject<HTMLElement>) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      el.scrollLeft += e.deltaY;
      e.preventDefault();
    };
    let startX = 0, startLeft = 0, down = false, dragged = false;
    const onDown = (e: PointerEvent) => {
      if (e.pointerType !== "mouse" || e.button !== 0) return;
      down = true; dragged = false;
      startX = e.clientX; startLeft = el.scrollLeft;
    };
    const onMove = (e: PointerEvent) => {
      if (!down) return;
      const dx = e.clientX - startX;
      if (!dragged && Math.abs(dx) < 5) return;
      dragged = true;
      el.scrollLeft = startLeft - dx;
    };
    const onUp = () => { down = false; };
    const onClick = (e: MouseEvent) => {
      if (dragged) { e.stopPropagation(); e.preventDefault(); dragged = false; }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    el.addEventListener("click", onClick, true);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      el.removeEventListener("click", onClick, true);
    };
  }, [ref]);
}
