import { useEffect, useState } from "react";

// The phone layout's width threshold -- the same 600px as the
// `@media (max-width: 600px)` blocks in styles.css, for the parts a
// stylesheet alone can't rearrange.
const QUERY = "(max-width: 600px)";

export function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(QUERY);
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return narrow;
}
