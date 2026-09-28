import { useEffect, useMemo, useRef, useState } from "react";
import type { InputHTMLAttributes, Ref } from "react";
import { api, StagedFile } from "../api";
import { PickedFile, entriesFrom, walkEntries } from "../uploads";
import { Vault, VaultError, VaultFile, encryptForUpload } from "../vault";
import { fmtSize } from "./StagingView";

/** Encrypted folders of Documents (VAULT.md): creating one, and working in
 *  one once unlocked. Nothing here ever sends a password or a key: the
 *  server gets encrypted names and encrypted bytes, and hands them back. */

const AREA = ":documents";
/** Locked again after this long without being used. */
const IDLE_MS = 15 * 60 * 1000;
const MIN_PASSWORD = 10;

// The unlocked vaults, by their folder: in this page's memory only, gone
// on reload, on Lock, or after IDLE_MS unused.
const unlocked = new Map<string, { vault: Vault; used: number }>();

/** Whether `path` is (still) unlocked -- without counting as a use. */
function isOpen(path: string): boolean {
  const hit = unlocked.get(path);
  if (hit && Date.now() - hit.used > IDLE_MS) unlocked.delete(path);
  return unlocked.has(path);
}

/** `path`'s key, if unlocked -- a use: it keeps the vault open. */
function keyFor(path: string): Vault | null {
  const hit = unlocked.get(path);
  if (!hit) return null;
  if (Date.now() - hit.used > IDLE_MS) { unlocked.delete(path); return null; }
  hit.used = Date.now();
  return hit.vault;
}

const message = (e: unknown) =>
  e instanceof VaultError ? e.message : String(e).replace(/^Error:\s*/, "").replace(/^\d+ [^—]*— /, "");

// What a decrypted file may be opened as in a tab; everything else is only
// ever saved. An HTML file opened here would run as this site.
const INLINE_TYPES: Record<string, string> = {
  pdf: "application/pdf", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif",
  webp: "image/webp", txt: "text/plain;charset=utf-8", mp3: "audio/mpeg", m4a: "audio/mp4",
  ogg: "audio/ogg", wav: "audio/wav", mp4: "video/mp4", webm: "video/webm",
};
const typeOf = (name: string) => INLINE_TYPES[name.split(".").pop()?.toLowerCase() ?? ""];

/** A file's size before encryption: its stored size less the header and a
 *  tag per chunk (VAULT.md). */
function plainSize(stored: number): number {
  const body = Math.max(0, stored - 64);
  return Math.max(0, body - 16 * Math.max(1, Math.ceil(body / (65536 + 16))));
}

/** Whether this browser can draw a text field as dots. */
const DOTS = typeof CSS !== "undefined" && CSS.supports("-webkit-text-security", "disc");

/** A vault password box the browser does not treat as a password. Chrome
 *  offers to save whatever is typed into a type="password" field, whatever
 *  its autocomplete says, and a vault password kept by the browser would
 *  undo the point of the vault. So it is a text field drawn as dots, which
 *  password managers leave alone too; a browser that cannot draw the dots
 *  gets a real password field rather than the password in the clear. */
function SecretInput({ inputRef, ...rest }: InputHTMLAttributes<HTMLInputElement> & { inputRef?: Ref<HTMLInputElement> }) {
  return (
    <input {...rest} ref={inputRef} type={DOTS ? "text" : "password"}
           className={"vault-secret" + (rest.className ? " " + rest.className : "")}
           autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false}
           data-lpignore="true" data-1p-ignore="true" data-bwignore="true" data-form-type="other" />
  );
}

function checkPassword(pw: string, again: string): string | null {
  if (pw.length < MIN_PASSWORD) return `At least ${MIN_PASSWORD} characters — a sentence is easier to remember than a code.`;
  if (pw !== again) return "The two passwords are not the same.";
  return null;
}

// ── creating one ────────────────────────────────────────────────────────
export function CreateVaultDialog({ parent, onClose, onCreated }: {
  parent: string;
  onClose: () => void;
  onCreated: (path: string) => void;
}) {
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<{ path: string; code: string } | null>(null);
  const [saved, setSaved] = useState(false);

  const create = async () => {
    const bad = !name.trim() ? "Give it a name." : checkPassword(pw, again);
    if (bad) { setError(bad); return; }
    setBusy(true); setError(null);
    try {
      const { file, vault, recoveryCode } = await Vault.create(pw);
      const r = await api.prepMakeVault(parent, name.trim(), file);
      unlocked.set(r.new_path, { vault, used: Date.now() });
      setMade({ path: r.new_path, code: recoveryCode });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal dish-info" onClick={(e) => e.stopPropagation()}>
        {!made ? (
          <>
            <h4>New encrypted folder{parent ? ` in ${parent}` : ""}</h4>
            <div className="dish-info-scroll vault-form">
              <p className="muted small">
                Its files and their names are encrypted here, in your browser, before they are uploaded: the
                server cannot read them, and nobody can open the folder without its password. It is private
                to you, for good.
              </p>
              <label>Name <input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
              <label>Password <SecretInput value={pw} onChange={(e) => setPw(e.target.value)} /></label>
              <label>Again <SecretInput value={again} onChange={(e) => setAgain(e.target.value)} /></label>
            </div>
            {error && <p className="error small">{error}</p>}
            <div className="row-actions">
              <button type="button" className="active" onClick={create} disabled={busy}>
                {busy ? "Creating…" : "Create"}
              </button>
              <button type="button" className="ghost" onClick={onClose} disabled={busy}>Cancel</button>
            </div>
          </>
        ) : (
          <>
            <h4>Your recovery code</h4>
            <div className="dish-info-scroll vault-form">
              <p className="small">
                If you forget the password, this code is the only way back in — not even the server's admin can
                open the folder without one of the two. Write it down or keep it in a password manager.
                <b> It is shown only now.</b>
              </p>
              <p className="vault-code">{made.code}</p>
              <button type="button" className="ghost" onClick={() => navigator.clipboard?.writeText(made.code)}>Copy</button>
              <label className="check-row">
                <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} /> I have saved it
              </label>
            </div>
            <div className="row-actions">
              <button type="button" className="active" disabled={!saved} onClick={() => onCreated(made.path)}>Done</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── working in one ──────────────────────────────────────────────────────
// Files to go into a vault that was locked when they were dropped on it
// (the tree's 🔐 row): kept, never sent, until it is unlocked.
export type VaultDrop = { path: string; files: PickedFile[] };

const TEXT_EXT = new Set(["txt", "md", "csv", "json", "log", "srt", "xml", "yaml", "yml", "ini", "tsv"]);
const ext = (name: string) => name.split(".").pop()?.toLowerCase() ?? "";

type Viewing = { path: string; name: string; url: string; kind: "image" | "audio" | "video" | "pdf" | "text" | "none"; text?: string };

function viewKind(name: string): Viewing["kind"] {
  const t = typeOf(name) ?? "";
  if (TEXT_EXT.has(ext(name))) return "text";
  if (t.startsWith("image/")) return "image";
  if (t.startsWith("audio/")) return "audio";
  if (t.startsWith("video/")) return "video";
  if (t === "application/pdf") return "pdf";
  return "none";
}

/** One vault, in the right-hand panel: locked, it asks for the password (or
 *  the recovery code); unlocked, it lists its folders and files by their
 *  real names and shows a picked file here, decrypted. Files and folders
 *  dropped on it are encrypted, names and all, before they go up. `files`
 *  is the whole Documents listing. */
export function VaultView({ path, files, upload, onChanged, incoming, onIncomingTaken }: {
  path: string;
  files: StagedFile[];
  upload: (picked: PickedFile[], folder: string) => void;
  onChanged: () => void;
  /** Dropped on its row in the tree: sent once it is unlocked. */
  incoming?: PickedFile[];
  onIncomingTaken?: () => void;
}) {
  const [vault, setVault] = useState<Vault | null>(() => keyFor(path));
  const [at, setAt] = useState(path);
  const [names, setNames] = useState<Record<string, string | null>>({});
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState<Viewing | null>(null);
  const [changing, setChanging] = useState(false);
  const [dragging, setDragging] = useState(false);
  const title = path.split("/").pop() ?? path;

  // Another vault picked: start from its top, locked unless already open.
  useEffect(() => { setVault(keyFor(path)); setAt(path); setNote(null); setViewing(null); }, [path]);
  // Locks itself once unused for IDLE_MS, even if left on screen.
  useEffect(() => {
    const t = window.setInterval(() => { if (!isOpen(path)) { setVault(null); setViewing(null); } }, 30_000);
    return () => window.clearInterval(t);
  }, [path]);
  // A decrypted file shown here lives as a blob URL: gone with it.
  useEffect(() => () => { if (viewing) URL.revokeObjectURL(viewing.url); }, [viewing]);
  const use = () => keyFor(path) ?? (setVault(null), null);

  const here = useMemo(() => files.filter((f) => f.folder === at), [files, at]);

  // The names, decrypted as they come into view.
  useEffect(() => {
    if (!vault) return;
    let alive = true;
    const todo = here.map((f) => f.name).filter((n) => !(n in names));
    if (!todo.length) return;
    Promise.all(todo.map((n) => vault.decryptName(n).then((p) => [n, p] as const, () => [n, null] as const)))
      .then((pairs) => { if (alive) setNames((m) => ({ ...m, ...Object.fromEntries(pairs) })); });
    return () => { alive = false; };
  }, [vault, here]);  // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (what: () => Promise<unknown>, done?: string) => {
    setBusy(true); setNote(null);
    try { await what(); if (done) setNote({ text: done }); onChanged(); }
    catch (e) { setNote({ text: message(e), bad: true }); }
    finally { setBusy(false); }
  };

  /** Encrypt what was picked or dropped -- loose files, or whole folders
   *  (relPath "A/B/c.txt") -- into the folder `into`, and queue it. A folder
   *  already there under the same name is reused; a file already there is
   *  skipped. */
  const send = (picked: PickedFile[], into: string) => {
    const v = use(); if (!v || !picked.length) return;
    run(async () => {
      const { files: ready, skipped } = await encryptForUpload(v, picked, into, files, names);
      const out: PickedFile[] = ready.map((r) => ({
        file: r.file, relPath: r.relPath,
        shownPath: [title, ...crumbs.map((c) => names[c] ?? "…"), r.plainPath].join("/"),
      }));
      if (out.length) upload(out, into);
      setNote({ text: `Encrypted ${out.length} file${out.length === 1 ? "" : "s"}, uploading` +
                      (skipped ? ` — ${skipped} skipped, already here` : "") });
    });
  };

  // Dropped on the tree's row while this was locked: sent once it opens.
  useEffect(() => {
    if (vault && incoming?.length) { send(incoming, path); onIncomingTaken?.(); }
  }, [vault, incoming]);  // eslint-disable-line react-hooks/exhaustive-deps

  const view = async (f: StagedFile, name: string) => {
    const v = use(); if (!v) return;
    setBusy(true); setNote(null);
    try {
      const plain = await v.decryptFile(await api.prepBytes(AREA, f.path));
      const kind = viewKind(name);
      setViewing({
        path: f.path, name, kind,
        url: URL.createObjectURL(new Blob([plain], { type: typeOf(name) ?? "application/octet-stream" })),
        text: kind === "text" ? new TextDecoder().decode(plain) : undefined,
      });
    } catch (e) {
      setNote({ text: message(e), bad: true });
    } finally {
      setBusy(false);
    }
  };
  const save = async (f: StagedFile, name: string) => {
    if (viewing?.path === f.path) {
      Object.assign(document.createElement("a"), { href: viewing.url, download: name }).click();
      return;
    }
    const v = use(); if (!v) return;
    setBusy(true); setNote(null);
    try {
      const plain = await v.decryptFile(await api.prepBytes(AREA, f.path));
      const url = URL.createObjectURL(new Blob([plain]));
      Object.assign(document.createElement("a"), { href: url, download: name }).click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      setNote({ text: message(e), bad: true });
    } finally {
      setBusy(false);
    }
  };

  const shown = here
    .map((f) => ({ f, name: names[f.name] }))
    .sort((a, b) => (a.f.kind === "folder" ? 0 : 1) - (b.f.kind === "folder" ? 0 : 1)
      || (a.name ?? "").localeCompare(b.name ?? "", undefined, { numeric: true }));
  const crumbs = at.slice(path.length).split("/").filter(Boolean);
  const taken = new Set(shown.map((x) => x.name));

  if (!vault) {
    return (
      <VaultUnlock path={path} title={title} waiting={incoming?.length ?? 0}
                   onOpen={(v) => { unlocked.set(path, { vault: v, used: Date.now() }); setVault(v); }} />
    );
  }

  const newFolder = () => {
    const name = window.prompt("New folder");
    const v = use();
    if (!name?.trim() || !v) return;
    if (taken.has(name.trim())) { setNote({ text: `${name.trim()} is already here`, bad: true }); return; }
    run(async () => api.prepMkdir(AREA, at, await v.encryptName(name.trim())));
  };
  const rename = (f: StagedFile, name: string) => {
    const to = window.prompt("Rename to", name);
    const v = use();
    if (!to?.trim() || to.trim() === name || !v) return;
    run(async () => api.prepRename(AREA, f.path, await v.encryptName(to.trim())));
  };
  const remove = (f: StagedFile, name: string) => {
    if (!window.confirm(`Delete ${name}${f.kind === "folder" ? " and everything in it" : ""}, for good?`)) return;
    if (viewing?.path === f.path) setViewing(null);
    run(() => api.prepDelete(AREA, f.path));
  };

  return (
    <div className={"mv-fileview vault-view" + (dragging ? " dropping" : "")}
         // Any click in here is using the vault: it keeps it open.
         onPointerDown={() => keyFor(path)}
         onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragging(true); } }}
         onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }}
         onDrop={(e) => {
           e.preventDefault(); e.stopPropagation(); setDragging(false);
           // Taken before the first await: the drop's contents go with the handler.
           const entries = entriesFrom(e.dataTransfer);
           const dt = e.dataTransfer;
           walkEntries(entries, dt).then((picked) => send(picked, at));
         }}>
      <div className="vault-head">
        <h2 title={path}>🔓 {title}</h2>
        <button className="ghost" onClick={() => { unlocked.delete(path); setVault(null); setViewing(null); }}>Lock</button>
      </div>
      <div className="vault-crumbs muted small">
        <button className="linkish" onClick={() => setAt(path)}>{title}</button>
        {crumbs.map((c, i) => (
          <span key={c}> / <button className="linkish" onClick={() => setAt([path, ...crumbs.slice(0, i + 1)].join("/"))}>
            {names[c] ?? "…"}</button></span>
        ))}
      </div>
      <div className="vault-toolbar">
        <label className="button-like">
          Upload files
          <input type="file" multiple hidden onChange={(e) => {
            send(Array.from(e.target.files ?? []).map((file) => ({ file, relPath: file.name })), at);
            e.target.value = "";
          }} />
        </label>
        <button className="ghost" onClick={newFolder} disabled={busy}>New folder</button>
        <button className="ghost" onClick={() => setChanging(!changing)}>Change password</button>
        {busy && <span className="muted small">Working…</span>}
      </div>
      {changing && <PasswordChange path={path} vault={vault} onDone={() => setChanging(false)} />}
      {note && <p className={(note.bad ? "error" : "muted") + " small"}>{note.text}</p>}

      <ul className="vault-list">
        {shown.map(({ f, name }) => (
          <li key={f.path} className={viewing?.path === f.path ? "active" : ""}>
            {name === undefined ? <span className="muted">…</span> : name === null ? (
              <span className="error small" title={f.name}>does not decrypt</span>
            ) : f.kind === "folder" ? (
              <button className="linkish" onClick={() => { setAt(f.path); setViewing(null); }}>📁 {name}</button>
            ) : (
              <button className="linkish" disabled={busy} onClick={() => view(f, name)}>📄 {name}</button>
            )}
            {f.kind !== "folder" && <span className="muted small">{fmtSize(plainSize(f.size))}</span>}
            {name && (
              <span className="vault-acts">
                {f.kind !== "folder" && <button className="ghost" disabled={busy} onClick={() => save(f, name)}>Save</button>}
                <button className="ghost" disabled={busy} onClick={() => rename(f, name)}>Rename</button>
                <button className="ghost danger" disabled={busy} onClick={() => remove(f, name)}>🗑</button>
              </span>
            )}
          </li>
        ))}
        {!shown.length && <li className="muted small">Empty — drop files or folders here, or use Upload files.</li>}
      </ul>

      {/* Pinned under the list, so it stays in sight however long the list is. */}
      {viewing && (
        <div className="vault-preview">
          <div className="vault-head">
            <b title={viewing.name}>{viewing.name}</b>
            <button className="ghost" onClick={() => setViewing(null)} title="Close">✕</button>
          </div>
          {viewing.kind === "image" && <img src={viewing.url} alt={viewing.name} />}
          {viewing.kind === "audio" && <audio src={viewing.url} controls autoPlay />}
          {viewing.kind === "video" && <video src={viewing.url} controls autoPlay />}
          {viewing.kind === "pdf" && <iframe src={viewing.url} title={viewing.name} />}
          {viewing.kind === "text" && <pre className="mv-filetext">{viewing.text}</pre>}
          {viewing.kind === "none" && <p className="muted small">No preview for this kind of file — Save it to open it.</p>}
        </div>
      )}

    </div>
  );
}

function VaultUnlock({ path, title, waiting, onOpen }: {
  path: string; title: string; waiting: number; onOpen: (v: Vault) => void;
}) {
  const [secret, setSecret] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // After the recovery code: a new password, before going in.
  const [reset, setReset] = useState<{ vault: Vault; file: VaultFile } | null>(null);
  const [pw, setPw] = useState(""), [again, setAgain] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const unlock = async () => {
    setBusy(true); setError(null);
    try {
      const file = await api.prepVault(path);
      const vault = await Vault.unlock(file, secret, recovery);
      if (recovery) setReset({ vault, file }); else onOpen(vault);
    } catch (e) {
      setError(message(e));
      input.current?.select();
    } finally {
      setBusy(false);
    }
  };
  const setNew = async () => {
    const bad = checkPassword(pw, again);
    if (bad || !reset) { setError(bad); return; }
    setBusy(true); setError(null);
    try {
      await api.prepSetVault(path, await reset.vault.withPassword(reset.file, pw));
      onOpen(reset.vault);
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };

  return (
    <div className="mv-fileview vault-view">
      <h2 title={path}>🔐 {title}</h2>
      {reset ? (
        <form className="vault-form" onSubmit={(e) => { e.preventDefault(); setNew(); }}>
          <p className="small">Recovery code accepted. Choose a new password.</p>
          <label>New password <SecretInput value={pw} onChange={(e) => setPw(e.target.value)} autoFocus /></label>
          <label>Again <SecretInput value={again} onChange={(e) => setAgain(e.target.value)} /></label>
          <button className="active" disabled={busy}>{busy ? "Saving…" : "Set password and open"}</button>
        </form>
      ) : (
        <form className="vault-form" onSubmit={(e) => { e.preventDefault(); unlock(); }}>
          <p className="muted small">Encrypted: the server cannot read it. Its password opens it here, in this page.</p>
          {waiting > 0 && (
            <p className="small">{waiting} file{waiting === 1 ? "" : "s"} waiting: unlock to encrypt and upload {waiting === 1 ? "it" : "them"}.</p>
          )}
          <label>{recovery ? "Recovery code" : "Password"}
            {recovery ? (
              <input ref={input} type="text" value={secret} autoFocus autoComplete="off" spellCheck={false}
                     onChange={(e) => setSecret(e.target.value)} />
            ) : (
              <SecretInput inputRef={input} value={secret} autoFocus onChange={(e) => setSecret(e.target.value)} />
            )}
          </label>
          <button className="active" disabled={busy || !secret}>{busy ? "Unlocking…" : "Unlock"}</button>
          <button type="button" className="linkish small" onClick={() => { setRecovery(!recovery); setSecret(""); setError(null); }}>
            {recovery ? "Use the password" : "Forgot the password? Use the recovery code"}
          </button>
        </form>
      )}
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

function PasswordChange({ path, vault, onDone }: { path: string; vault: Vault; onDone: () => void }) {
  const [pw, setPw] = useState(""), [again, setAgain] = useState("");
  const [state, setState] = useState<{ text: string; bad?: boolean } | null>(null);
  const save = async () => {
    const bad = checkPassword(pw, again);
    if (bad) { setState({ text: bad, bad: true }); return; }
    setState({ text: "Saving…" });
    try {
      await api.prepSetVault(path, await vault.withPassword(await api.prepVault(path), pw));
      onDone();
    } catch (e) { setState({ text: message(e), bad: true }); }
  };
  return (
    <form className="vault-form vault-box" onSubmit={(e) => { e.preventDefault(); save(); }}>
      <label>New password <SecretInput value={pw} onChange={(e) => setPw(e.target.value)} autoFocus /></label>
      <label>Again <SecretInput value={again} onChange={(e) => setAgain(e.target.value)} /></label>
      <div className="vault-toolbar">
        <button className="active">Save</button>
        <button type="button" className="ghost" onClick={onDone}>Cancel</button>
      </div>
      {state && <span className={(state.bad ? "error" : "muted") + " small"}>{state.text}</span>}
    </form>
  );
}
