import { ReactNode, useEffect, useState } from "react";
import { hasAuth, login, upgradeLegacyCookie } from "./auth";

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
      else if (status === 429) setError("Too many wrong passwords — try again later, or use the token.");
      else setError(usePassword ? "Wrong username or password." : "Wrong username or token.");
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login" onSubmit={submit}>
        <h1>Sign in</h1>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          {usePassword ? "Password" : "Token"}
          <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)}
                 autoComplete={usePassword ? "current-password" : "off"} />
        </label>
        {error && <p className="error small">{error}</p>}
        <button disabled={busy || !username || !secret}>{busy ? "Checking…" : "Sign in"}</button>
        <button type="button" className="linkish login-switch"
                onClick={() => { setUsePassword(!usePassword); setSecret(""); setError(null); }}>
          {usePassword ? "Use the token instead" : "Use a password instead"}
        </button>
      </form>
    </div>
  );
}
