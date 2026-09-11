// Credential lives in the `diary_auth` cookie as base64("username:token").
// The backend accepts it from that cookie (or an Authorization: Basic header).

const COOKIE = "diary_auth";
const MAX_AGE = 60 * 60 * 24 * 365; // 1 year

export function hasAuth(): boolean {
  return readCookie(COOKIE) !== null;
}

/** Username from the stored credential (`base64("user:token")`), or null. */
export function currentUsername(): string | null {
  const v = readCookie(COOKIE);
  if (!v) return null;
  try {
    return atob(v).split(":")[0] || null;
  } catch {
    return null;
  }
}

export function setAuth(username: string, token: string): void {
  const value = btoa(`${username}:${token}`);
  document.cookie =
    `${COOKIE}=${value}; path=/; max-age=${MAX_AGE}; SameSite=Strict` +
    (location.protocol === "https:" ? "; Secure" : "");
}

export function clearAuth(): void {
  document.cookie = `${COOKIE}=; path=/; max-age=0; SameSite=Strict`;
}

/** Called by the api layer on a 401 — drops the bad cookie and tells the gate. */
export function onAuthFailed(): void {
  clearAuth();
  window.dispatchEvent(new Event("diary-auth-failed"));
}

/** User-initiated sign-out: clear the credential and drop back to the login gate. */
export function logout(): void {
  clearAuth();
  window.dispatchEvent(new Event("diary-auth-failed"));
}

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? m[1] : null;
}
