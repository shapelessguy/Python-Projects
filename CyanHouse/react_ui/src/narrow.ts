import { useEffect, useState } from "react";

// ── Phone mode: the one rule for the whole app ──────────────────────────
// The app is in phone mode when the window is at most 700px wide OR at most
// 700px tall (a phone held sideways is wide but short). Nothing else decides
// it: change PHONE_QUERY and every panel follows.
//
//  * CSS: <html> carries the class `phone` while it holds, so a phone rule
//    is written `html.phone .foo { ... }` -- never with its own @media width
//    or height. (A sideways phone is `@media (orientation: landscape)`
//    around `html.phone` rules.)
//  * Code: usePhone() for what a stylesheet can't rearrange (a pager
//    instead of a column of charts, a menu instead of a row of tabs);
//    isPhone() outside React.
//
// Breakpoints that are about room on a desktop (two charts a row from
// 1000px, the Movies columns stacking under 1100px) are not phone mode
// and keep their own @media.
export const PHONE_QUERY = "(max-width: 700px), (max-height: 700px)";

const mq = window.matchMedia(PHONE_QUERY);

export function isPhone(): boolean {
  return mq.matches;
}

// The class is set before the first render (main.tsx imports this module)
// and follows the window from then on.
const mark = () => document.documentElement.classList.toggle("phone", mq.matches);
mark();
mq.addEventListener("change", mark);

export function usePhone(): boolean {
  const [phone, setPhone] = useState(mq.matches);
  useEffect(() => {
    const onChange = () => setPhone(mq.matches);
    mq.addEventListener("change", onChange);
    onChange();
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return phone;
}
