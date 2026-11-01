import { useEffect, useState } from "react";
import { api } from "./api";

/** The same rule the server applies (api/passwords.py), checked here first
 *  so the reason shows as you type rather than after a round trip. */
export function passwordProblem(p: string): string | null {
  if (p.length < 9) return "at least 9 characters";
  if (!/\p{Lu}/u.test(p)) return "at least one uppercase letter";
  if (!/\d/.test(p)) return "at least one number";
  return null;
}

/** Sets, changes or removes the signed-in user's own password — the one the
 *  sign-in screen swaps for their token. */
export function PasswordDialog({ onClose }: { onClose: () => void }) {
  const [has, setHas] = useState<boolean | null>(null);
  const [first, setFirst] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    api.me().then((me) => setHas(!!me.has_password)).catch(() => setHas(false));
  }, []);

  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [busy]);

  const problem = first ? passwordProblem(first) : null;
  const mismatch = again !== "" && again !== first;

  const run = async (call: () => Promise<{ has_password: boolean }>, message: string) => {
    setBusy(true);
    setError("");
    try {
      setHas((await call()).has_password);
      setFirst(""); setAgain("");
      setDone(message);
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  };

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || problem || !first || first !== again) return;
    run(() => api.setPassword(first), has ? "Password changed." : "Password set.");
  };

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <form className="modal password-form" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h4>{has ? "Change password" : "Set a password"}</h4>
        <p className="muted small">
          Lets you sign in with your username and this password instead of the token, on the browser and on Android.
        </p>
        <label>
          New password
          <input type="password" autoComplete="new-password" value={first} autoFocus
                 onChange={(e) => { setFirst(e.target.value); setDone(""); }} />
        </label>
        <label>
          Again
          <input type="password" autoComplete="new-password" value={again}
                 onChange={(e) => { setAgain(e.target.value); setDone(""); }} />
        </label>
        {problem && <p className="muted small">Needs {problem}.</p>}
        {!problem && mismatch && <p className="muted small">The two don't match.</p>}
        {error && <p className="error small">{error}</p>}
        {done && <p className="small">{done}</p>}
        <div className="password-actions">
          {has && (
            <button type="button" className="linkish" disabled={busy}
                    onClick={() => run(api.removePassword, "Password removed — only the token signs you in now.")}>
              Remove password
            </button>
          )}
          <button type="button" className="ghost" disabled={busy} onClick={onClose}>Close</button>
          <button disabled={busy || has === null || !first || !!problem || first !== again}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}
