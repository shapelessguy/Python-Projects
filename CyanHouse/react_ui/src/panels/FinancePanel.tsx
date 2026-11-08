import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  api, Currency, FinCategory, FinExecuted, FinForecast, FinKind, FinSnapshot, RecurFreq, useVersionPoll,
} from "../api";
import { useBackToClose } from "../backClose";
import { readCookie, writeCookie } from "../cookies";
import { Key, useT } from "../i18n";
import { ConfirmDialog } from "../ConfirmDialog";
import { usePhone } from "../narrow";
import { Icon, IconName } from "./icons";
import { CatIcon, IconPicker } from "./IconPicker";
import { Floating } from "./Floating";
import { CalEntry, DIR_COLOR, DIR_SIGN, directionBy, FinanceCalendar } from "./FinanceCalendar";

// The currency picked last, offered first on the next new payment or
// forecast (EUR until one is picked).
const CURRENCY_COOKIE = "finance_currency";
const lastCurrency = (): Currency => (readCookie(CURRENCY_COOKIE) === "USD" ? "USD" : "EUR");
const CURRENCIES: Currency[] = ["EUR", "USD"];
const FREQS: RecurFreq[] = ["daily", "weekly", "monthly", "yearly"];
// "Every 4 weeks" when the step is above one, else "Weekly" (as Calendar's).
const EVERY: Record<RecurFreq, Key> = {
  daily: "cal_every_days", weekly: "cal_every_weeks", monthly: "cal_every_months", yearly: "cal_every_years",
};
const repeatText = (t: ReturnType<typeof useT>["t"], freq: RecurFreq, n: number) =>
  n > 1 ? t(EVERY[freq], { n }) : t(`cal_${freq}`);

const today = () => new Date().toLocaleDateString("en-CA");
// All payments are loaded (for searching and totals); the list draws this
// many at a time, newest first, and "Load more" draws the next lot.
const PAGE = 30;

// "12,50" or "12.50" -> 1250; anything else -> NaN.
function toCents(text: string): number {
  const n = Number(text.trim().replace(",", "."));
  return text.trim() && Number.isFinite(n) ? Math.round(n * 100) : NaN;
}

/** Categories in tree order (parents first, siblings by sort), each with
 *  its path ("Home › Rent") for lists and pickers. */
function useCategoryTree(cats: FinCategory[]) {
  return useMemo(() => {
    const byId = new Map(cats.map((c) => [c.id, c]));
    const label = (c: FinCategory): string => {
      const parent = c.parent_id != null ? byId.get(c.parent_id) : undefined;
      return parent ? label(parent) + " › " + c.name : c.name;
    };
    const ordered: { cat: FinCategory; depth: number; label: string }[] = [];
    const walk = (parent: number | null, depth: number) => {
      cats.filter((c) => c.parent_id === parent).forEach((c) => {
        ordered.push({ cat: c, depth, label: label(c) });
        walk(c.id, depth + 1);
      });
    };
    walk(null, 0);
    const name = (id: number | null) => {
      const o = id == null ? undefined : ordered.find((x) => x.cat.id === id);
      return id == null ? null : o ? <><CatIcon icon={o.cat.icon} /> {o.label}</> : "?";
    };
    return { ordered, name };
  }, [cats]);
}

type Tree = ReturnType<typeof useCategoryTree>;
type Editing = { kind: FinKind; id: number | null } | null;   // id null: a new one

// The three lists, each opened over the page from its button.
// Two lists: categories, and payments (the recurring ones — forecasts — in a
// drawer at the payments' top).
const SHEETS: { kind: FinKind; icon: string }[] = [
  { kind: "categories", icon: "🗂️" },
  { kind: "executed", icon: "🧾" },
];

/** Personal's Finance section. The three lists — categories, forecasts, the
 *  payments — open over the page from buttons on Personal's tab row
 *  (`toolsSlot`, where they are portalled); behind them, the payments'
 *  calendar (still to come). */
export function FinancePanel({ toolsSlot }: { toolsSlot: HTMLElement | null }) {
  const { t, lang } = useT();
  const versions = useVersionPoll();
  const [shown, setShown] = useState(PAGE);
  const [recurringOpen, setRecurringOpen] = useState(false);
  // A payment opened from the calendar — a new one on a day, or one tapped
  // (a recurring one's date edits its rule) — in a window of its own.
  const [quick, setQuick] = useState<{ date: string } | { entry: CalEntry } | null>(null);
  const [data, setData] = useState<FinSnapshot | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [sheet, setSheet] = useState<FinKind | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    // Already this new (a change of ours brought it back): nothing to fetch.
    if (data && versions.finance <= data.version) return;
    api.finance().then(setData).catch((e) => setError(String(e.message ?? e)));
  }, [versions.finance]);   // eslint-disable-line react-hooks/exhaustive-deps

  const tree = useCategoryTree(data?.categories ?? []);
  // Income, spending, transfer: by which side of a payment is an account.
  const direction = useMemo(() => {
    const accounts = new Set((data?.categories ?? []).filter((c) => c.kind === "account").map((c) => c.id));
    return directionBy((id) => id != null && accounts.has(id));
  }, [data?.categories]);

  const phone = usePhone();
  // True when it went through (a form over the calendar then closes).
  const apply = (p: Promise<FinSnapshot>) =>
    p.then((d) => { setData(d); setEditing(null); setError(""); return true; })
      .catch((e) => { setError(String(e.message ?? e)); return false; });
  const save = (kind: FinKind, id: number | null, body: object) =>
    apply(id == null ? api.financeCreate(kind, body) : api.financeUpdate(kind, id, body));
  // Deleting asks first, in the app's own dialog.
  const [deleting, setDeleting] = useState<{ kind: FinKind; id: number } | null>(null);
  const remove = (kind: FinKind, id: number) => setDeleting({ kind, id });
  const money = (cents: number, currency: Currency) =>
    (cents / 100).toLocaleString(lang, { style: "currency", currency });
  const day = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString(lang);
  // A card's from or to: the category's own icon and name, its full path
  // ("Home › Rent") on hover. `small` (under a reason): just the icon, when
  // it has one.
  const side = (id: number | null, small = false) => {
    const o = id == null ? undefined : tree.ordered.find((x) => x.cat.id === id);
    if (!o) return <span className="fin-pay-side"><em className="fin-pay-name muted">{id == null ? t("fin_outside") : "?"}</em></span>;
    return (
      <span className="fin-pay-side" title={o.label}>
        <CatIcon icon={o.cat.icon} />{!(small && o.cat.icon) && <span className="fin-pay-name">{o.cat.name}</span>}
      </span>
    );
  };
  // A payment or a forecast as a card, the amount at its right. On top its
  // reason, when it has one, with `when` (its date, or how it repeats) and
  // from → to under it, smaller; without one, from → to on top.
  // A recurring one (a forecast: a rule, not a payment) is drawn apart:
  // dashed, see-through, with ↻ by its amount.
  const payCard = (p: FinExecuted | FinForecast, when: (string | null | false)[], buttons: () => ReactNode, recurring = false) => {
    const flow = (small: boolean) => (
      <span className="fin-pay-flow">
        {side(p.from_id, small)}
        <span className="fin-pay-arrow" aria-hidden>→</span>
        {side(p.to_id, small)}
      </span>
    );
    const whenText = when.filter(Boolean).join(" · ");
    return (
      <div key={p.id} className={"fin-cat-card fin-pay-card" + (recurring ? " recurring" : "")}>
        <div className="fin-pay-main">
          {p.justification ? <div className="fin-pay-title">{p.justification}</div> : flow(true)}
          <div className="fin-pay-meta">
            <span className="fin-pay-when">{whenText}</span>
            {p.justification && <>{whenText && <span aria-hidden>·</span>}{flow(true)}</>}
          </div>
        </div>
        <span className="fin-pay-amount" style={{ color: DIR_COLOR[direction(p)] }}>
          {recurring && <span className="fin-pay-recur" aria-hidden>↻</span>}{DIR_SIGN[direction(p)]}{money(p.amount_cents, p.currency)}
        </span>
        <span className="fin-cat-actions">{buttons()}</span>
      </div>
    );
  };
  const isEditing = (kind: FinKind, id: number | null) => editing?.kind === kind && editing.id === id;
  const close = () => setEditing(null);

  const sheetTitle: Record<FinKind, string> = {
    categories: t("fin_categories"), forecasts: t("fin_forecasts"), executed: t("fin_payments"),
  };
  const openSheet = (kind: FinKind) => { setEditing(null); setError(""); setSheet(kind); };
  const catName = (id: number | null) =>
    id == null ? t("fin_outside") : data?.categories.find((c) => c.id === id)?.name ?? "?";
  const closeSheet = () => { setEditing(null); setError(""); setSheet(null); };

  // On Personal's tab row, pushed to its right: icon + name on a wide
  // screen, the icon alone on a phone.
  const tools = (
    <span className="fin-tools">
      {SHEETS.map((s) => (
        <button key={s.kind} className={sheet === s.kind ? "active" : ""} title={sheetTitle[s.kind]}
                aria-label={sheetTitle[s.kind]} onClick={() => openSheet(s.kind)}>
          <span className="mv-tabicon" aria-hidden>{s.icon}</span>
          <span className="mv-tablabel">{sheetTitle[s.kind]}</span>
        </button>
      ))}
    </span>
  );

  // Edit and delete: words on a wide screen, icons on a phone.
  const actions = (kind: FinKind, id: number) => phone ? <>
    <button className="ghost icon-only" title={t("edit")} aria-label={t("edit")}
            onClick={() => setEditing({ kind, id })}><Icon name="edit" size={18} className="" /></button>
    <button className="ghost icon-only" title={t("delete")} aria-label={t("delete")}
            onClick={() => remove(kind, id)}><Icon name="trash" size={18} className="" /></button>
  </> : <>
    <button className="ghost" onClick={() => setEditing({ kind, id })}>{t("edit")}</button>
    <button className="ghost" onClick={() => remove(kind, id)}>{t("delete")}</button>
  </>;

  const body = (kind: FinKind) => {
    if (!data) return <p className="muted">{error || t("loading")}</p>;
    if (kind === "categories") return <>
      {isEditing("categories", null) &&
        <CategoryForm tree={tree} onSave={(b) => save("categories", null, b)} onCancel={close} />}
      <CategoryCards
        cats={data.categories}
        actions={(id) => actions("categories", id)}
        form={(cat) => isEditing("categories", cat.id) &&
          <CategoryForm cat={cat} tree={tree} onSave={(b) => save("categories", cat.id, b)} onCancel={close} />}
        onMove={(parent, ids) => apply(api.financeMove(parent, ids))}
      />
    </>;
    // Payments, under a closed drawer of the recurring ones. One "+" and one
    // form for both: what it repeats (and when) decides which it saves.
    const forecastCard = (fc: FinForecast) => isEditing("forecasts", fc.id) ? (
      <PaymentForm key={fc.id} kind="forecasts" row={fc} tree={tree}
                   onSave={(_, b) => save("forecasts", fc.id, b)} onCancel={close} />
    ) : payCard(fc, [
      fc.recur_freq ? repeatText(t, fc.recur_freq, fc.recur_interval) : day(fc.start_date),
      fc.recur_freq && `${t("fin_since")} ${day(fc.start_date)}` + (fc.recur_until ? ` → ${day(fc.recur_until)}` : ""),
      fc.generated_until && `${t("fin_written_until")} ${day(fc.generated_until)}`,
    ], () => actions("forecasts", fc.id), true);
    return <>
      {isEditing("executed", null) &&
        <PaymentForm tree={tree} onSave={(k, b) => save(k, null, b)} onCancel={close} />}
      {data.forecasts.length > 0 && (
        <div className="fin-drawer fin-drawer-top">
          <button className="fin-drawer-head" aria-expanded={recurringOpen} onClick={() => setRecurringOpen(!recurringOpen)}>
            <span className="fin-drawer-icon" aria-hidden>🔁</span>
            <span className="fin-drawer-label">{t("fin_recurring")}</span>
            <span className="fin-drawer-count">{data.forecasts.length}</span>
            <span className={"fin-drawer-caret" + (recurringOpen ? " open" : "")} aria-hidden>▾</span>
          </button>
          {recurringOpen && <div className="fin-cats fin-recurring">{data.forecasts.map(forecastCard)}</div>}
        </div>
      )}
      <div className="fin-cats">
        {data.executed.slice(0, shown).map((ex) => isEditing("executed", ex.id) ? (
          <PaymentForm key={ex.id} kind="executed" row={ex} tree={tree}
                       onSave={(_, b) => save("executed", ex.id, b)} onCancel={close} />
        ) : payCard(ex, [day(ex.date)], () => actions("executed", ex.id)))}
        {!data.executed.length && !isEditing("executed", null) && <p className="muted">{t("fin_no_payments")}</p>}
        {shown < data.executed.length && (
          <button className="ghost fin-more" onClick={() => setShown(shown + PAGE)}>
            {t("fin_load_more", { n: data.executed.length - shown })}
          </button>
        )}
      </div>
    </>;
  };

  return (
    <div className="panel finance">
      {data ? (
        <FinanceCalendar
          executed={data.executed} forecasts={data.forecasts}
          money={(p) => money(p.amount_cents, p.currency)}
          direction={direction}
          title={(p) => p.justification || catName(direction(p) === "out" ? p.to_id : direction(p) === "in" ? p.from_id : p.to_id)}
          onAdd={(date) => { setError(""); setQuick({ date }); }}
          onOpen={(entry) => { setError(""); setQuick({ entry }); }}
        />
      ) : <p className="muted">{error || t("loading")}</p>}
      {toolsSlot && createPortal(tools, toolsSlot)}
      {deleting && (
        <ConfirmDialog message={t("fin_confirm_delete")} yesLabel={t("delete")} danger onNo={() => setDeleting(null)}
                       onYes={() => { apply(api.financeDelete(deleting.kind, deleting.id)); setDeleting(null); }} />
      )}
      {quick && data && (() => {
        const close = () => { setQuick(null); setError(""); };
        const done = (ok: boolean) => { if (ok) setQuick(null); };
        const e = "entry" in quick ? quick.entry : null;
        return (
          <FinSheet onClose={close} title={
            !e ? t("fin_new_payment") : e.kind === "forecasts" ? t("fin_edit_recurring") : t("fin_edit_payment")}>
            {error && <p className="fin-error">{error}</p>}
            {e ? (
              <PaymentForm kind={e.kind} row={e.p} tree={tree} onCancel={close}
                           onSave={(k, b) => apply(api.financeUpdate(k, e.p.id, b)).then(done)} />
            ) : (
              <PaymentForm tree={tree} date={"date" in quick ? quick.date : undefined} onCancel={close}
                           onSave={(k, b) => apply(api.financeCreate(k, b)).then(done)} />
            )}
          </FinSheet>
        );
      })()}
      {sheet && (
        <FinSheet title={sheetTitle[sheet]} onClose={closeSheet} action={
          <button className="ghost icon-only fin-add" title={t("fin_new")} aria-label={t("fin_new")}
                  onClick={() => { setError(""); setEditing({ kind: sheet, id: null }); }}>+</button>
        }>
          {error && <p className="fin-error">{error}</p>}
          {body(sheet)}
        </FinSheet>
      )}
    </div>
  );
}

/** One list over the page: a dialog on a wide screen, the whole screen with
 *  a back bar on a phone. Back closes it either way. `action` sits at the
 *  title's right (a "+" for a new one). */
function FinSheet({ title, onClose, action, children }: {
  title: string; onClose: () => void; action?: ReactNode; children: ReactNode;
}) {
  const { t } = useT();
  const narrow = usePhone();
  useBackToClose(onClose);
  if (narrow) return (
    <div className="modal-backdrop settings-full">
      <div className="settings-full-page fin-sheet-page">
        <div className="fin-back-row">
          <button className="ghost back-bar" onClick={onClose}>
            <Icon name="left" size={16} className="back-bar-arrow" />
            <span className="back-bar-name">{title}</span>
          </button>
          {action}
        </div>
        <div className="fin-sheet-body">{children}</div>
      </div>
    </div>
  );
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal fin-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="fin-sheet-head">
          <h4>{title}</h4>
          {action}
          <button className="ghost icon-only" title={t("close")} aria-label={t("close")} onClick={onClose}>
            <Icon name="close" size={16} className="" />
          </button>
        </div>
        <div className="fin-sheet-body">{children}</div>
      </div>
    </div>
  );
}

function CategoryForm({ cat, tree, onSave, onCancel }: {
  cat?: FinCategory; tree: Tree; onSave: (body: object) => void; onCancel: () => void;
}) {
  const { t } = useT();
  const [name, setName] = useState(cat?.name ?? "");
  const [icon, setIcon] = useState(cat?.icon ?? "");
  const [parent, setParent] = useState<number | null>(cat?.parent_id ?? null);
  const [kind, setKind] = useState<FinCategory["kind"]>(cat?.kind ?? "");
  const values = { name, icon, parent_id: parent, kind };
  // A new one put under an account is most likely an account too.
  const pickParent = (id: number | null) => {
    setParent(id);
    if (!cat && id != null) setKind(tree.ordered.find((o) => o.cat.id === id)?.cat.kind ?? "");
  };
  // Archiving asks first (in the app's dialog); bringing one back doesn't.
  // Either saves the form too.
  const [asking, setAsking] = useState(false);
  const archive = () => {
    if (cat?.archived) onSave({ ...values, archived: false });
    else setAsking(true);
  };
  return (
    <form className="fin-form fin-cat-form" onSubmit={(e) => {
      e.preventDefault();
      onSave(values);
    }}>
      <div className="fin-field">{t("fin_icon")}<IconPicker value={icon} onChange={setIcon} /></div>
      <label>{t("fin_name")}<input value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label>{t("fin_parent")}
        <CategorySelect tree={tree} value={parent} onChange={pickParent} empty="—" exclude={cat?.id} />
      </label>
      <label>{t("fin_kind")}
        <select value={kind} onChange={(e) => setKind(e.target.value as FinCategory["kind"])}>
          <option value="">—</option>
          <option value="account">{t("fin_kind_account")}</option>
        </select>
      </label>
      <FormButtons onCancel={onCancel} archive={cat && { archived: cat.archived, onClick: archive }} />
      {asking && (
        <ConfirmDialog message={t("fin_confirm_archive")} yesLabel={t("fin_archive")} onNo={() => setAsking(false)}
                       onYes={() => { setAsking(false); onSave({ ...values, archived: true }); }} />
      )}
    </form>
  );
}

/** A form's buttons: Cancel and Save at the right, and — editing a category —
 *  Archive (or Restore) at the left. Icons on a phone, icon and word on a
 *  wide screen. */
function FormButtons({ onCancel, archive }: {
  onCancel: () => void; archive?: { archived: boolean; onClick: () => void };
}) {
  const { t } = useT();
  const phone = usePhone();
  const button = (cls: string, icon: IconName, label: string, props: object) => (
    <button className={"fin-btn " + cls + (phone ? " icon-only" : "")} title={label} aria-label={label} {...props}>
      <Icon name={icon} size={phone ? 20 : 16} className="" />
      {!phone && <span>{label}</span>}
    </button>
  );
  return (
    <div className="fin-form-actions">
      {archive && (archive.archived
        ? button("fin-btn-archive", "unarchive", t("fin_unarchive"), { type: "button", onClick: archive.onClick })
        : button("fin-btn-archive", "archive", t("fin_archive"), { type: "button", onClick: archive.onClick }))}
      <span className="fin-form-actions-end">
        {button("fin-btn-cancel", "close", t("cancel"), { type: "button", onClick: onCancel })}
        {button("fin-btn-save", "tick", t("save"), { type: "submit" })}
      </span>
    </div>
  );
}

// A card's indent per level, and how far sideways a drag goes for one level.
const INDENT = 24;

type Row = { cat: FinCategory; depth: number };
type Drop = { index: number; depth: number; min: number; max: number };

/** Depth-first rows under `parent`, each with its depth; `skip` leaves a
 *  category out with everything under it. */
function flatten(cats: FinCategory[], parent: number | null, depth: number, keep: (c: FinCategory) => boolean,
                 skip?: number): Row[] {
  return cats.filter((c) => c.parent_id === parent && c.id !== skip && keep(c))
    .flatMap((c) => [{ cat: c, depth }, ...flatten(cats, c.id, depth + 1, keep, skip)]);
}

/** The categories as cards, a sub-category indented under its parent.
 *  Dragging one (with the mouse, or after a long press on a phone) takes it
 *  and everything under it along: up and down picks its place, sideways its
 *  level — the anchors on its gap show the levels it can take there (a
 *  category at the top, under the card above, or under one of that card's
 *  parents). Saved on drop. Archived ones (with whatever sits under them)
 *  wait in a closed drawer at the bottom. `form` is a card's edit form while
 *  it is open. */
function CategoryCards({ cats, actions, form, onMove }: {
  cats: FinCategory[]; actions: (id: number) => ReactNode; form: (cat: FinCategory) => ReactNode;
  onMove: (parent: number | null, ids: number[]) => Promise<unknown>;
}) {
  const { t } = useT();
  // The categories as moved, from the drop until the saved ones come back.
  const [moved, setMoved] = useState<FinCategory[] | null>(null);
  const [drag, setDrag] = useState<{ id: number; drop: Drop; top: number; height: number } | null>(null);
  const [drawer, setDrawer] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const cards = useRef(new Map<number, HTMLDivElement>());
  // While a drag is on, a finger moving must not scroll the page. Chrome
  // only waits for a touchmove listener that was there when the touch began,
  // so this one stays on the list for good and acts only during a drag.
  const dragging = useRef(false);
  useEffect(() => {
    const box = list.current;
    if (!box) return;
    const touchMove = (ev: TouchEvent) => { if (dragging.current && ev.cancelable) ev.preventDefault(); };
    box.addEventListener("touchmove", touchMove, { passive: false });
    return () => box.removeEventListener("touchmove", touchMove);
  }, []);

  const shown = moved ?? cats;
  const byId = new Map(shown.map((c) => [c.id, c]));
  const active = (c: FinCategory) => !c.archived;
  const rows = flatten(shown, null, 0, active);
  const dragged = drag ? [{ cat: byId.get(drag.id)!, depth: 0 }, ...flatten(shown, drag.id, 1, active)] : [];
  const draggedIds = new Set(dragged.map((r) => r.cat.id));
  // The drawer's: archived ones with nothing archived above them, each with all under it.
  const archivedTops = shown.filter((c) => {
    if (!c.archived) return false;
    for (let p = c.parent_id; p != null; p = byId.get(p)?.parent_id ?? null) if (byId.get(p)?.archived) return false;
    return true;
  });

  const startDrag = (e: React.PointerEvent, cat: FinCategory, depth: number) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button, input, select, a, form")) return;
    const box = list.current, card = cards.current.get(cat.id);
    if (!box || !card) return;
    const id = e.pointerId, x0 = e.clientX, y0 = e.clientY, touch = e.pointerType !== "mouse";
    // The grip (a phone's) starts at once; the rest of the card after a long press.
    const now = !!(e.target as HTMLElement).closest(".fin-cat-grip");
    const grab = y0 - card.getBoundingClientRect().top;
    // It floats with everything under it: the gap is that tall.
    const under = flatten(shown, cat.id, 1, active);
    const last = under.length ? cards.current.get(under[under.length - 1].cat.id) : card;
    const height = (last ?? card).getBoundingClientRect().bottom - card.getBoundingClientRect().top;
    // The rows it can go between: everything but itself and what is under it.
    const others = flatten(shown, null, 0, active, cat.id);
    let drop: Drop | null = null;

    const project = (x: number, y: number) => {
      // Its gap: after every card whose middle is above the pointer.
      const index = others.filter((r) => {
        const b = cards.current.get(r.cat.id)?.getBoundingClientRect();
        return b && b.top + b.height / 2 < y;
      }).length;
      const prev = others[index - 1], next = others[index];
      const max = prev ? prev.depth + 1 : 0;
      const min = next ? next.depth : 0;
      const want = depth + Math.round((x - x0) / INDENT);
      const d = Math.min(max, Math.max(min, want));
      const r = box.getBoundingClientRect();
      const top = Math.min(Math.max(y - grab - r.top, 0), Math.max(r.height - height, 0));
      drop = { index, depth: d, min, max };
      setDrag({ id: cat.id, drop, top, height });
    };
    const begin = () => { dragging.current = true; project(x0, y0); navigator.vibrate?.(15); };
    const timer = touch && !now ? window.setTimeout(begin, 350) : 0;
    if (touch && now) begin();
    const move = (ev: PointerEvent) => {
      if (ev.pointerId !== id) return;
      if (!dragging.current) {
        if (Math.hypot(ev.clientX - x0, ev.clientY - y0) < (touch ? 8 : 4)) return;
        if (touch) { stop(); return; }   // moved before the long press: a scroll
        begin();
      }
      project(ev.clientX, ev.clientY);
    };
    const noMenu = (ev: Event) => ev.preventDefault();
    const stop = () => {
      window.clearTimeout(timer);
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      document.removeEventListener("pointercancel", cancel);
      document.removeEventListener("contextmenu", noMenu);
      dragging.current = false;
      setDrag(null);
    };
    const up = (ev: PointerEvent) => {
      if (ev.pointerId !== id) return;
      stop();
      if (!drop) return;
      // Its new parent: the nearest card above one level up.
      const { index, depth: d } = drop;
      let parent: number | null = null;
      if (d > 0) for (let i = index - 1; i >= 0; i--) if (others[i].depth === d - 1) { parent = others[i].cat.id; break; }
      const before = others.slice(0, index).filter((r) => r.cat.parent_id === parent && r.depth === d).map((r) => r.cat.id);
      const after = others.slice(index).filter((r) => r.cat.parent_id === parent && r.depth === d).map((r) => r.cat.id);
      const ids = [...before, cat.id, ...after];
      const siblings = shown.filter((c) => c.parent_id === parent && active(c)).map((c) => c.id);
      if (parent === cat.parent_id && ids.join() === siblings.join()) return;
      setMoved(shown.map((c) => {
        const n = ids.indexOf(c.id);
        return n < 0 ? c : { ...c, parent_id: c.id === cat.id ? parent : c.parent_id, sort: n };
      }).sort((a, b) => a.sort - b.sort || a.id - b.id));
      onMove(parent, ids).finally(() => setMoved(null));
    };
    const cancel = (ev: PointerEvent) => { if (ev.pointerId === id) stop(); };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
    document.addEventListener("pointercancel", cancel);
    if (touch) document.addEventListener("contextmenu", noMenu);
  };

  // `hidden`: the dragged ones' own cards stay in the page while it floats
  // (a touch's events keep going to the card it began on).
  const card = (r: Row, draggable: boolean, ghost = false, hidden = false) => (
    <div key={r.cat.id} className="fin-cat-row" style={{ paddingLeft: r.depth * INDENT, display: hidden ? "none" : undefined }}>
      {form(r.cat) || (
        <div ref={ghost ? undefined : (el) => { if (el) cards.current.set(r.cat.id, el); else cards.current.delete(r.cat.id); }}
             className={"fin-cat-card" + (draggable ? " draggable" : "")}
             onPointerDown={draggable ? (e) => startDrag(e, r.cat, r.depth) : undefined}>
          {draggable && <span className="fin-cat-grip" aria-hidden>⠿</span>}
          <CatIcon icon={r.cat.icon} />
          <span className="fin-cat-name">{r.cat.name}</span>
          {r.cat.kind === "account" &&
            <span className="fin-kind-badge" title={t("fin_kind_account")} aria-label={t("fin_kind_account")}>{t("fin_kind_account")[0]}</span>}
          <span className="fin-cat-actions">{actions(r.cat.id)}</span>
        </div>
      )}
    </div>
  );

  // Where it would land: a gap the size of its card, with an anchor for
  // every level it can take there, the picked one lit.
  const gap = drag && (
    <div key="gap" className="fin-cat-gap" style={{ height: drag.height }}>
      {Array.from({ length: drag.drop.max - drag.drop.min + 1 }, (_, i) => drag.drop.min + i).map((d) => (
        <span key={d} className={"fin-cat-anchor" + (d === drag.drop.depth ? " on" : "")} style={{ left: d * INDENT + 8 }} />
      ))}
      <span className="fin-cat-slot" style={{ left: drag.drop.depth * INDENT }} />
    </div>
  );
  // The gap goes before the drop.index-th card not being dragged.
  const body: ReactNode[] = [];
  let n = 0;
  for (const r of rows) {
    const hidden = draggedIds.has(r.cat.id);
    if (drag && !hidden && n++ === drag.drop.index) body.push(gap);
    body.push(card(r, true, false, hidden));
  }
  if (drag && n <= drag.drop.index) body.push(gap);

  return (
    <div className={"fin-cats" + (drag ? " dragging" : "")}>
      <div className="fin-cat-list-box" ref={list}>
        {body}
        {drag && (
          <div className="fin-cat-float" style={{ top: drag.top, left: drag.drop.depth * INDENT }}>
            {dragged.map((r) => card(r, false, true))}
          </div>
        )}
      </div>
      {archivedTops.length > 0 && (
        <div className="fin-drawer">
          <button className="fin-drawer-head" aria-expanded={drawer} onClick={() => setDrawer(!drawer)}>
            <span className="fin-drawer-icon" aria-hidden>🗄️</span>
            <span className="fin-drawer-label">{t("fin_archived_list")}</span>
            <span className="fin-drawer-count">{archivedTops.length}</span>
            <span className={"fin-drawer-caret" + (drawer ? " open" : "")} aria-hidden>▾</span>
          </button>
          {drawer && (
            <div className="fin-cats fin-archived">
              {archivedTops.flatMap((c) => [{ cat: c, depth: 0 }, ...flatten(shown, c.id, 1, () => true)])
                .map((r) => card(r, false))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** A payment (kind "executed") or a forecast: the same template, plus a date
 *  for one and a start and repetition for the other. A new one (no `kind`)
 *  offers the repetition too, and saves as a forecast when it repeats or its
 *  date is still to come, else as a payment. */
function PaymentForm({ kind, row, tree, date: startDate, onSave, onCancel }: {
  kind?: "executed" | "forecasts"; row?: FinExecuted | FinForecast; tree: Tree; date?: string;
  onSave: (kind: "executed" | "forecasts", body: object) => void; onCancel: () => void;
}) {
  const { t } = useT();
  const fc = kind === "forecasts" ? (row as FinForecast | undefined) : undefined;
  const ex = kind === "executed" ? (row as FinExecuted | undefined) : undefined;
  const [date, setDate] = useState(ex?.date ?? fc?.start_date ?? startDate ?? today());
  // Opened from the calendar, it may sit far down the list: bring it into view.
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => { formRef.current?.scrollIntoView({ block: "nearest" }); }, []);
  const [from, setFrom] = useState<number | null>(row?.from_id ?? null);
  const [to, setTo] = useState<number | null>(row?.to_id ?? null);
  const [amount, setAmount] = useState(row ? (row.amount_cents / 100).toFixed(2) : "");
  const [currency, setCurrency] = useState<Currency>(row?.currency ?? lastCurrency());
  const [why, setWhy] = useState(row?.justification ?? "");
  const [freq, setFreq] = useState<RecurFreq | null>(fc ? fc.recur_freq : null);
  const [interval, setInterval] = useState(String(fc?.recur_interval ?? 1));
  const [until, setUntil] = useState(fc?.recur_until ?? "");
  const [error, setError] = useState("");

  const pick = (value: number | null, set: (v: number | null) => void) =>
    <CategorySelect tree={tree} value={value} onChange={set} empty={t("fin_outside")} />;

  return (
    <form className="fin-form fin-pay-form" ref={formRef} onSubmit={(e) => {
      e.preventDefault();
      const cents = toCents(amount);
      if (!(cents > 0)) { setError(t("fin_err_amount")); return; }
      writeCookie(CURRENCY_COOKIE, currency);
      const body = { from_id: from, to_id: to, amount_cents: cents, currency, justification: why };
      // A new one: repeating, or still to come, makes a forecast (it writes
      // the payments as they fall due); anything else is a payment now.
      const as = kind ?? (freq || date > today() ? "forecasts" : "executed");
      onSave(as, as === "executed" ? { ...body, date } : {
        ...body, start_date: date, recur_freq: freq,
        recur_interval: parseInt(interval, 10) || 1, recur_until: freq && until ? until : null,
      });
    }}>
      <label>{freq && kind !== "executed" ? t("fin_start") : t("fin_date")}
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
      </label>
      <label>{t("fin_from")}{pick(from, setFrom)}</label>
      <label>{t("fin_to")}{pick(to, setTo)}</label>
      {/* The amount and its currency share a row. */}
      <label>{t("fin_amount")}
        <span className="fin-pair">
          <input className="fin-amount fin-pair-main" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <select className="fin-pair-side" value={currency} aria-label={t("fin_currency")} onChange={(e) => setCurrency(e.target.value as Currency)}>
            {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </span>
      </label>
      <label>{t("fin_justification")}<input value={why} onChange={(e) => setWhy(e.target.value)} /></label>
      {kind !== "executed" && <>
        {/* How often, and every how many of those: the choices read "Every 4
            weeks" as the number changes. */}
        <label>{t("cal_repeat")}
          <span className="fin-pair">
            <select className="fin-pair-main" value={freq ?? ""} onChange={(e) => setFreq((e.target.value || null) as RecurFreq | null)}>
              <option value="">{t("cal_no_repeat")}</option>
              {FREQS.map((f) => <option key={f} value={f}>{repeatText(t, f, Math.max(1, parseInt(interval, 10) || 1))}</option>)}
            </select>
            {freq && <>
              <input type="number" min={1} className="fin-pair-side" aria-label={t("fin_every")} value={interval}
                     onChange={(e) => setInterval(e.target.value)} />
            </>}
          </span>
        </label>
        {freq && <label>{t("cal_until_label")}<input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>}
      </>}
      {error && <span className="fin-error">{error}</span>}
      <FormButtons onCancel={onCancel} />
    </form>
  );
}

/** A category dropdown that draws each one's icon (a native <select> can only
 *  hold text): a button with the current one's icon and path, opening the
 *  tree of them all. `empty` names the no-category choice; `exclude` drops
 *  a category and everything under it (a category's own parent picker). */
function CategorySelect({ tree, value, onChange, empty, exclude }: {
  tree: Tree; value: number | null; onChange: (id: number | null) => void; empty: string; exclude?: number;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  useBackToClose(() => setOpen(false), open);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => {
      const at = e.target as Node;
      if (!box.current?.contains(at) && !pop.current?.contains(at)) setOpen(false);
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);

  // tree.ordered is depth-first, so a category's descendants are the rows
  // right after it that sit deeper.
  const shown = useMemo(() => {
    const out: Tree["ordered"] = [];
    let skipDepth: number | null = null;
    for (const o of tree.ordered) {
      if (skipDepth != null && o.depth > skipDepth) continue;
      skipDepth = null;
      if (o.cat.id === exclude) { skipDepth = o.depth; continue; }
      out.push(o);
    }
    return out;
  }, [tree, exclude]);

  const pick = (id: number | null) => { onChange(id); setOpen(false); };
  return (
    <span className="fin-cat-select" ref={box}>
      <button type="button" ref={btn} className={"fin-cat-btn" + (open ? " active" : "")} onClick={() => setOpen(!open)}>
        {value == null ? <span className="muted">{empty}</span> : tree.name(value)}
        <span className="fin-caret" aria-hidden>▾</span>
      </button>
      {open && (
        <Floating anchor={btn} ref={pop} className="fin-cat-list">
          <button type="button" className={value == null ? "active" : ""} onClick={() => pick(null)}>
            <span className="muted">{empty}</span>
          </button>
          {shown.map((o) => (
            <button type="button" key={o.cat.id} className={o.cat.id === value ? "active" : ""}
                    style={{ paddingLeft: 8 + o.depth * 18 }} onClick={() => pick(o.cat.id)}>
              <CatIcon icon={o.cat.icon} /> {o.cat.name}
            </button>
          ))}
        </Floating>
      )}
    </span>
  );
}
