import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

/**
 * A text field showing the server's value, except while it is being edited:
 * the page polls every second and would otherwise overwrite what is typed.
 * Each change is committed after `delay` ms of quiet, and on blur/Enter.
 */
export function SyncedInput({
  value,
  onCommit,
  delay = 500,
  multiline = false,
  validate,
  ...rest
}: {
  value: string;
  onCommit: (v: string) => void;
  delay?: number;
  multiline?: boolean;
  validate?: (v: string) => boolean;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const [draft, setDraft] = useState(value);
  const editing = useRef(false);
  const timer = useRef<number>();
  const committed = useRef(value);

  useEffect(() => {
    if (!editing.current) setDraft(value);
    committed.current = value;
  }, [value]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const commit = (v: string) => {
    window.clearTimeout(timer.current);
    if (v === committed.current || (validate && !validate(v))) return;
    committed.current = v;
    onCommit(v);
  };

  const change = (v: string) => {
    setDraft(v);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => commit(v), delay);
  };

  const common = {
    value: draft,
    onFocus: () => (editing.current = true),
    onBlur: () => {
      editing.current = false;
      commit(draft);
    },
  };

  if (multiline) {
    return (
      <textarea
        {...common}
        className={rest.className}
        placeholder={rest.placeholder}
        disabled={rest.disabled}
        onChange={(e) => change(e.target.value)}
      />
    );
  }
  return (
    <input
      {...rest}
      {...common}
      onChange={(e) => change(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit(draft);
        rest.onKeyDown?.(e);
      }}
    />
  );
}

/** A toggle switch (a checkbox underneath, for keyboard and screen readers). */
export function Switch({
  checked,
  onChange,
  disabled,
  title,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  title?: string;
  label?: string;
}) {
  return (
    <label className={`switch ${disabled ? "disabled" : ""}`} title={title}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={label ?? title}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="track">
        <span className="thumb" />
      </span>
    </label>
  );
}

export function Card({
  title,
  aside,
  children,
  className,
}: {
  title: ReactNode;
  aside?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className ?? ""}`}>
      <header className="card-head">
        <h3>{title}</h3>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** Boxes into `count` columns, each added to the shortest one, so a box keeps its own height. */
export function Masonry<T>({
  items,
  count,
  weight,
  render,
}: {
  items: T[];
  count: number;
  weight: (item: T) => number;
  render: (item: T) => ReactNode;
}) {
  const columns: T[][] = Array.from({ length: count }, () => []);
  const heights = new Array(count).fill(0);
  for (const item of items) {
    const i = heights.indexOf(Math.min(...heights));
    columns[i].push(item);
    heights[i] += weight(item);
  }
  return (
    <div className="masonry">
      {columns.map((col, i) => (
        <div className="masonry-col" key={i}>
          {col.map(render)}
        </div>
      ))}
    </div>
  );
}

export function useColumns(): number {
  const [width, setWidth] = useState(window.innerWidth);
  useEffect(() => {
    const on = () => setWidth(window.innerWidth);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return width < 640 ? 1 : width < 1000 ? 2 : 3;
}

// ---- Toasts: what a click did, at the bottom of the page ----

type Toast = { id: number; text: string; error: boolean };
const ToastCtx = createContext<(text: string, error?: boolean) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(0);
  const push = (text: string, error = false) => {
    const id = next.current++;
    setToasts((t) => [...t.slice(-3), { id, text, error }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), error ? 6000 : 3000);
  };
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.error ? "error" : ""}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
