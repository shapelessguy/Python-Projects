// Sign-in. The credential lives in the `diary_auth` cookie as
// base64("username:token"), set by the server (POST /api/login) as HttpOnly,
// so no script on the page can read it. What the page can read is
// `diary_user`, the name alone, set beside it. The backend also accepts an
// Authorization: Basic header (Android).

const AUTH_COOKIE = "diary_auth";
const USER_COOKIE = "diary_user";

export function hasAuth(): boolean {
  return readCookie(USER_COOKIE) !== null || readCookie(AUTH_COOKIE) !== null;
}

/** Username of the signed-in user, or null. */
export function currentUsername(): string | null {
  const v = readCookie(USER_COOKIE);
  return v ? decodeURIComponent(v) : null;
}

function postLogin(username: string, token: string): Promise<Response> {
  return fetch("/api/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, token }),
    cache: "no-store",
  });
}

/** Signs in; true when the server accepted the credential and set the cookie. */
export async function login(username: string, token: string): Promise<boolean> {
  return (await postLogin(username, token)).ok;
}

/** A credential from before the cookie became HttpOnly is still readable
 *  here: sign in with it once, which replaces it with the HttpOnly one. */
export async function upgradeLegacyCookie(): Promise<void> {
  const v = readCookie(AUTH_COOKIE);
  if (!v) return;
  // Only a refusal signs out. Anything else (a backend not yet restarted
  // onto /api/login, the network) leaves the old cookie working, to be
  // upgraded on a later load.
  let cred: string;
  try {
    cred = atob(v);
  } catch {
    onAuthFailed();
    return;
  }
  const colon = cred.indexOf(":");
  const user = cred.slice(0, colon), token = cred.slice(colon + 1);
  try {
    if ((await postLogin(user, token)).status === 401) onAuthFailed();
  } catch { /* try again next time */ }
}

export function clearAuth(): void {
  fetch("/api/logout", { method: "POST", cache: "no-store" }).catch(() => {});
  // The name, and any old script-set credential, go now; the HttpOnly one
  // goes with the answer to the request above.
  for (const name of [USER_COOKIE, AUTH_COOKIE]) {
    document.cookie = `${name}=; path=/; max-age=0; SameSite=Strict`;
  }
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
