import { useEffect, useState } from "react";

// When the phone layout applies -- narrow, or short (a phone held
// sideways is wider than 600px) -- the same as the `@media` blocks in
// styles.css, for the parts a stylesheet alone can't rearrange.
const QUERY = "(max-width: 600px), (max-height: 500px)";

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
