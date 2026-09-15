// Small shared cookie helpers -- auth.ts/panels/grocery.ts/alarms.ts each
// grew their own copy of this; this is the shared version for new callers.
const DEFAULT_MAX_AGE = 60 * 60 * 24 * 365; // 1 year

export function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

export function writeCookie(name: string, value: string, maxAgeSeconds = DEFAULT_MAX_AGE): void {
  document.cookie =
    `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSeconds}; SameSite=Strict` +
    (location.protocol === "https:" ? "; Secure" : "");
}
