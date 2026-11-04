import { ReactNode, useEffect, useState } from "react";
import { hasAuth, login, upgradeLegacyCookie } from "./auth";
import { useT } from "./i18n";

export function LoginGate({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(hasAuth());

  useEffect(() => {
    upgradeLegacyCookie();
  }, []);

  useEffect(() => {
    const drop = () => setAuthed(false);
    window.addEventListener("diary-auth-failed", drop);
    return () => window.removeEventListener("diary-auth-failed", drop);
  }, []);

  if (authed) return <>{children}</>;
  return <LoginForm onDone={() => setAuthed(true)} />;
}

function LoginForm({ onDone }: { onDone: () => void }) {
  const { t } = useT();
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [usePassword, setUsePassword] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !secret || busy) return;
    setBusy(true);
    setError(null);
    try {
      const status = await login(username.trim(),
        usePassword ? { password: secret } : { token: secret.trim() });
      if (status === 200) onDone();
      else if (status === 429) setError(t("login_too_many"));
      else setError(t(usePassword ? "login_wrong_password" : "login_wrong_token"));
    } catch {
      setError(t("login_unreachable"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login" onSubmit={submit}>
        <h1>{t("sign_in")}</h1>
        <label>
          {t("username")}
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          {usePassword ? t("password") : t("token")}
          <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)}
                 autoComplete={usePassword ? "current-password" : "off"} />
        </label>
        {error && <p className="error small">{error}</p>}
        <button disabled={busy || !username || !secret}>{busy ? t("login_checking") : t("sign_in")}</button>
        <button type="button" className="linkish login-switch"
                onClick={() => { setUsePassword(!usePassword); setSecret(""); setError(null); }}>
          {t(usePassword ? "login_use_token" : "login_use_password")}
        </button>
      </form>
    </div>
  );
}
