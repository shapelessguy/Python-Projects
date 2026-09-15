import { ReactNode, useState } from "react";
import { api, Column, ColType, MonthData } from "../api";

const TYPES: ColType[] = ["number", "text", "bool", "enum"];

const parseOptions = (s: string): string[] =>
  s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);

function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h4>{title}</h4>
        {children}
      </div>
    </div>
  );
}

interface Ask {
  message: string;
  confirmLabel: string;
  onYes: () => void;
}

function ConfirmModal({ ask, onDone }: { ask: Ask; onDone: () => void }) {
  return (
    <Modal title="Confirm" onClose={onDone}>
      <p>{ask.message}</p>
      <div className="row-actions">
        <button
          className="danger"
          autoFocus
          onClick={() => {
            ask.onYes();
            onDone();
          }}
        >
          {ask.confirmLabel}
        </button>
        <button className="ghost" onClick={onDone}>
          Cancel
        </button>
      </div>
    </Modal>
  );
}

export function ColumnManager({
  columns,
  units,
  month,
  onState,
}: {
  columns: Column[];
  units: string[];
  month: string;
  onState: (snapshot: MonthData) => void;
}) {
  const [open, setOpen] = useState(false); // start retracted
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ask, setAsk] = useState<Ask | null>(null);

  // Every call here returns the full month snapshot; apply it straight away.
  const run = (p: Promise<MonthData>) => {
    setBusy(true);
    setErr(null);
    p.then(onState)
      .catch((e) => setErr(String(e)))
      .finally(() => setBusy(false));
  };

  return (
    <aside className={"col-manager" + (open ? "" : " collapsed")}>
      <button className="col-manager-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "Columns ›" : "‹"}
      </button>
      {open && (
        <div className="col-manager-body">
          {err && (
            <p className="error small" onClick={() => setErr(null)}>
              {err}
            </p>
          )}
          {columns.map((c) => (
            <ColumnRow
              key={c.key}
              column={c}
              units={units}
              busy={busy}
              onSave={(patch) => run(api.patchColumn(c.key, patch, month))}
              onDelete={() =>
                setAsk({
                  message: `Delete column “${c.name}” and all its saved data?`,
                  confirmLabel: "Delete column",
                  onYes: () => run(api.deleteColumn(c.key, month)),
                })
              }
              onUnitAdded={(u) => api.addUnit(u, month).then(onState)}
            />
          ))}
          <AddColumn
            units={units}
            busy={busy}
            onAdd={(body) => run(api.addColumn(body, month))}
            onUnitAdded={(u) => api.addUnit(u, month).then(onState)}
          />

          <details className="col-row">
            <summary>Units ({units.filter((u) => u).length})</summary>
            <ul className="unit-list">
              {units.filter((u) => u).map((u) => (
                <li key={u}>
                  <span>{u}</span>
                  <button
                    className="danger"
                    title="Remove from the pick-list"
                    onClick={() =>
                      setAsk({
                        message: `Remove unit “${u}” from the pick-list? Columns already using it keep their label.`,
                        confirmLabel: "Remove unit",
                        onYes: () =>
                          api.deleteUnit(u, month).then(onState).catch((e) => setErr(String(e))),
                      })
                    }
                  >
                    ✕
                  </button>
                </li>
              ))}
              {units.filter((u) => u).length === 0 && <li className="muted">none</li>}
            </ul>
          </details>
        </div>
      )}
      {ask && <ConfirmModal ask={ask} onDone={() => setAsk(null)} />}
    </aside>
  );
}

function UnitField({
  value,
  units,
  onChange,
  onAddUnit,
}: {
  value: string;
  units: string[];
  onChange: (v: string) => void;
  onAddUnit: (u: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const options = units.includes(value) || !value ? units : [...units, value];

  const save = async () => {
    const u = draft.trim();
    if (!u || saving) return;
    setSaving(true);
    try {
      await onAddUnit(u);
      onChange(u);
      setOpen(false);
      setDraft("");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="unit-field">
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((u) => (
          <option key={u} value={u}>
            {u || "—"}
          </option>
        ))}
      </select>
      <button type="button" className="ghost" onClick={() => { setDraft(""); setOpen(true); }}>
        + new
      </button>
      {open && (
        <Modal title="New unit" onClose={() => setOpen(false)}>
          <input
            autoFocus
            value={draft}
            placeholder="e.g. bpm"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") setOpen(false);
            }}
          />
          <div className="row-actions">
            <button disabled={!draft.trim() || saving} onClick={save}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button className="ghost" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ColumnRow({
  column,
  units,
  busy,
  onSave,
  onDelete,
  onUnitAdded,
}: {
  column: Column;
  units: string[];
  busy: boolean;
  onSave: (patch: Partial<Column>) => void;
  onDelete: () => void;
  onUnitAdded: (u: string) => Promise<unknown>;
}) {
  const [name, setName] = useState(column.name);
  const [description, setDescription] = useState(column.description);
  const [unit, setUnit] = useState(column.unit);
  const [type, setType] = useState<ColType>(column.type);
  const [optionsText, setOptionsText] = useState(column.options.join("\n"));
  const dirty =
    name !== column.name ||
    description !== column.description ||
    unit !== column.unit ||
    type !== column.type ||
    optionsText !== column.options.join("\n");

  return (
    <details className="col-row">
      <summary>
        {column.name}
        {column.unit ? ` (${column.unit})` : ""}
      </summary>
      <label>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label>
        Description
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </label>
      <label>
        Unit
        <UnitField value={unit} units={units} onChange={setUnit} onAddUnit={onUnitAdded} />
      </label>
      <label>
        Type
        <select value={type} onChange={(e) => setType(e.target.value as ColType)}>
          {TYPES.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      {type === "enum" && (
        <label>
          Values (one per line)
          <textarea
            value={optionsText}
            onChange={(e) => setOptionsText(e.target.value)}
            rows={3}
          />
        </label>
      )}
      <div className="row-actions">
        <button
          disabled={busy || !dirty}
          onClick={() =>
            onSave({ name, description, unit, type, options: parseOptions(optionsText) })
          }
        >
          Save
        </button>
        <button className="danger" disabled={busy} onClick={onDelete}>
          Delete
        </button>
      </div>
    </details>
  );
}

function AddColumn({
  units,
  busy,
  onAdd,
  onUnitAdded,
}: {
  units: string[];
  busy: boolean;
  onAdd: (body: Partial<Column>) => void;
  onUnitAdded: (u: string) => Promise<unknown>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("");
  const [type, setType] = useState<ColType>("number");
  const [optionsText, setOptionsText] = useState("");

  return (
    <details className="col-row add">
      <summary>➕ Add column</summary>
      <label>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label>
        Description
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </label>
      <label>
        Unit
        <UnitField value={unit} units={units} onChange={setUnit} onAddUnit={onUnitAdded} />
      </label>
      <label>
        Type
        <select value={type} onChange={(e) => setType(e.target.value as ColType)}>
          {TYPES.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      {type === "enum" && (
        <label>
          Values (one per line)
          <textarea
            value={optionsText}
            onChange={(e) => setOptionsText(e.target.value)}
            rows={3}
          />
        </label>
      )}
      <div className="row-actions">
        <button
          disabled={busy || !name.trim()}
          onClick={() => {
            onAdd({
              name: name.trim(),
              description: description.trim(),
              unit,
              type,
              options: parseOptions(optionsText),
            });
            setName("");
            setDescription("");
            setUnit("");
            setType("number");
            setOptionsText("");
          }}
        >
          Add
        </button>
      </div>
    </details>
  );
}
