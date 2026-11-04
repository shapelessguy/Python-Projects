import { useEffect, useState } from "react";
import { api } from "./api";
import { useBackToClose } from "./backClose";
import { Key, useT } from "./i18n";

/** The same rule the server applies (api/passwords.py), checked here first
 *  so the reason shows as you type rather than after a round trip. */
export function passwordProblem(p: string): Key | null {
  if (p.length < 9) return "password_needs_length";
  if (!/\p{Lu}/u.test(p)) return "password_needs_upper";
  if (!/\d/.test(p)) return "password_needs_digit";
  return null;
}

/** Sets, changes or removes the signed-in user's own password — the one the
 *  sign-in screen swaps for their token. */
export function PasswordDialog({ onClose }: { onClose: () => void }) {
  useBackToClose(onClose);
  const { t } = useT();
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
    run(() => api.setPassword(first), t(has ? "password_changed" : "password_set"));
  };

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <form className="modal password-form" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h4>{t(has ? "change_password" : "password_set_title")}</h4>
        <p className="muted small">{t("password_intro")}</p>
        <label>
          {t("password_new")}
          <input type="password" autoComplete="new-password" value={first} autoFocus
                 onChange={(e) => { setFirst(e.target.value); setDone(""); }} />
        </label>
        <label>
          {t("password_again")}
          <input type="password" autoComplete="new-password" value={again}
                 onChange={(e) => { setAgain(e.target.value); setDone(""); }} />
        </label>
        {problem && <p className="muted small">{t(problem)}</p>}
        {!problem && mismatch && <p className="muted small">{t("password_mismatch")}</p>}
        {error && <p className="error small">{error}</p>}
        {done && <p className="small">{done}</p>}
        <div className="password-actions">
          {has && (
            <button type="button" className="linkish" disabled={busy}
                    onClick={() => run(api.removePassword, t("password_removed"))}>
              {t("password_remove")}
            </button>
          )}
          <button type="button" className="ghost" disabled={busy} onClick={onClose}>{t("close")}</button>
          <button disabled={busy || has === null || !first || !!problem || first !== again}>
            {busy ? t("saving") : t("save")}
          </button>
        </div>
      </form>
    </div>
  );
}
