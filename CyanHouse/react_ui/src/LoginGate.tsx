import { ReactNode, useEffect, useState } from "react";
import { api } from "./api";
import { clearAuth, hasAuth, setAuth } from "./auth";

export function LoginGate({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(hasAuth());

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
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !token || busy) return;
    setBusy(true);
    setError(null);
    setAuth(username.trim(), token.trim());
    try {
      await api.version(); // validates the cookie
      onDone();
    } catch {
      clearAuth();
      setError("Wrong username or token.");
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
          Token
          <input type="password" value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
        {error && <p className="error small">{error}</p>}
        <button disabled={busy || !username || !token}>{busy ? "Checking…" : "Sign in"}</button>
      </form>
    </div>
  );
}
