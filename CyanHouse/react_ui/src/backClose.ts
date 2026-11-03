/**
 * The phone's Back button closes the overlay on top instead of leaving the
 * page: each open overlay holds one history entry (same URL, nothing in
 * it). Back pops it and closes the newest overlay; an overlay closed any
 * other way (its button, the backdrop, a save) takes its entry back off.
 *
 * The entries carry nothing, so which one goes doesn't matter: only that
 * there is one per open overlay. history.back() is asynchronous -- its
 * popstate comes later, and an entry pushed before then would be the one
 * it removes -- so pushes wait until the pending Backs have landed.
 */
import { useEffect, useRef } from "react";

const open: { close: () => void }[] = [];
let ownBacks = 0;    // our history.back()s whose popstate hasn't come yet
let waiting = 0;     // pushes held until then

window.addEventListener("popstate", () => {
  if (ownBacks > 0) {
    if (--ownBacks === 0) for (; waiting > 0; waiting--) history.pushState(null, "");
    return;
  }
  open.pop()?.close();
});

/** Back closes this overlay while `active` (for one shown conditionally). */
export function useBackToClose(onClose: () => void, active = true) {
  const latest = useRef(onClose);
  latest.current = onClose;
  useEffect(() => {
    if (!active) return;
    const entry = { close: () => latest.current() };
    open.push(entry);
    if (ownBacks > 0) waiting++;
    else history.pushState(null, "");
    return () => {
      const i = open.indexOf(entry);
      if (i < 0) return;  // Back closed it: its entry is gone already
      open.splice(i, 1);
      if (waiting > 0) waiting--;
      else { ownBacks++; history.back(); }
    };
  }, [active]);
}
